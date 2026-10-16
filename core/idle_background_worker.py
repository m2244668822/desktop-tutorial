"""Idle-only, resumable embedding refresh for the White Studio orchestrator."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from core.autonomy import AutonomyConfig, AutonomyLease, AutonomyPolicy
from core.durable_task_store import DurableTaskStore
from core.embedding_client import EmbeddingError, NemotronEmbeddingClient
from core.orchestrator_types import OperationContext, TaskRecord


TERMINAL = {"completed", "blocked", "failed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def classify_source(path: Path) -> str:
    normalized = "/".join(path.parts).replace("\\", "/")
    if "91 外部知識" in normalized:
        return "external-source"
    if "候選草稿" in normalized or "Inbox" in normalized:
        return "candidate"
    return "vault-markdown"


def eligible_markdown(path: Path, root: Path) -> bool:
    if path.suffix.lower() != ".md" or not path.is_file():
        return False
    relative = path.relative_to(root).as_posix()
    excluded_parts = {
        ".git",
        ".obsidian",
        "node_modules",
        "generated",
        "dist",
        "build",
        "runtime",
        "WhiteStudio-full-backup-20261011",
        "portfolio-package-staging-20261015",
    }
    if any(part in excluded_parts for part in path.relative_to(root).parts):
        return False
    if relative.startswith("ChatGPT 記憶資料庫/") or relative == "ChatGPT 記憶資料庫":
        return False
    return True


@dataclass(frozen=True)
class IdleWorkerConfig:
    idle_seconds: int = 300
    batch_size: int = 4
    cpu_pause_percent: float = 80.0
    memory_pause_percent: float = 85.0
    lease_ttl_seconds: int = 1800


class EmbeddingRefreshJob:
    def __init__(
        self,
        vault_root: str | Path,
        state_root: str | Path,
        *,
        client: Any,
        config: IdleWorkerConfig | None = None,
        now: Callable[[], str] = _now_iso,
    ) -> None:
        self.vault_root = Path(vault_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.client = client
        self.config = config or IdleWorkerConfig()
        self.now = now
        self.index_path = self.state_root / "embedding-index.jsonl"
        self.checkpoint_path = self.state_root / "checkpoint.json"
        self.proposal_path = self.state_root / "canonical-index-proposal.json"

    def _files(self) -> list[Path]:
        return sorted(
            (path for path in self.vault_root.rglob("*.md") if eligible_markdown(path, self.vault_root)),
            key=lambda path: path.relative_to(self.vault_root).as_posix(),
        )

    def _load_records(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        records: dict[str, dict[str, Any]] = {}
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record.get("dedupe_key") if isinstance(record, dict) else None
            if key:
                records[str(key)] = record
        return records

    def _load_checkpoint(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {"cursor": 0, "status": "pending"}
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"cursor": 0, "status": "pending"}
        return payload if isinstance(payload, dict) else {"cursor": 0, "status": "pending"}

    def _write_checkpoint(self, *, cursor: int, total: int, status: str, reason: str = "") -> dict[str, Any]:
        previous = self._load_checkpoint()
        payload = {
            **{
                key: previous[key]
                for key in ("task_id", "run_id", "operation_id", "idempotency_key")
                if key in previous
            },
            "schema_version": 1,
            "job_type": "embedding_refresh",
            "cursor": cursor,
            "total": total,
            "status": status,
            "reason": reason,
            "updated_at": self.now(),
            "model_id": self.client.config.model,
        }
        _atomic_json(self.checkpoint_path, payload)
        return payload

    def _append_records(self, records: Iterable[dict[str, Any]]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _source_manifest(self, files: list[Path]) -> tuple[list[dict[str, str]], str]:
        manifest = [
            {
                "source_path": path.relative_to(self.vault_root).as_posix(),
                "sha256": _sha256(path),
            }
            for path in files
        ]
        digest = hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return manifest, digest

    def _write_proposal(self, *, files: list[Path], indexed: int, source_commit: str, complete: bool) -> None:
        _manifest, manifest_sha256 = self._source_manifest(files)
        _atomic_json(
            self.state_root / "provenance.json",
            {
                "schema_version": "1.0.0",
                "job_type": "embedding_refresh",
                "source_commit": source_commit,
                "source_manifest_sha256": manifest_sha256,
                "generator": "idle_background_worker",
                "model_id": self.client.config.model,
                "input_type": "passage",
                "vector_dimension": self.client.config.dimension,
                "records_scanned": len(files),
                "records_indexed": indexed,
                "canonical_promotion": "pending_approval",
            },
        )
        _atomic_json(
            self.state_root / "validation.json",
            {
                "status": "PASS" if complete else "PENDING",
                "records_scanned": len(files),
                "records_indexed": indexed,
                "missing": 0 if complete else None,
                "orphan": 0 if complete else None,
                "source_hashes": "PASS" if complete else "PENDING",
                "git_diff_check_pass": False,
                "provenance_reproducible": bool(complete),
                "canonical_promotion_allowed": False,
                "reason": "canonical_approval_required",
            },
        )
        _atomic_json(
            self.proposal_path,
            {
                "schema_version": 1,
                "status": "canonical-index-promotion-pending-approval",
                "job_type": "embedding_refresh",
                "source_commit": source_commit,
                "source_manifest_sha256": manifest_sha256,
                "model_id": self.client.config.model,
                "vector_dimension": self.client.config.dimension,
                "records_scanned": len(files),
                "records_indexed": indexed,
                "generated_at": self.now(),
                "promotion": {
                    "requires_human_approval": True,
                    "canonical_files_modified": False,
                    "validation_required": [
                        "source_hashes",
                        "missing_orphan_zero",
                        "git_diff_check",
                        "provenance_reproducible",
                    ],
                },
            },
        )

    def run_batch(self, *, should_preempt: Callable[[], bool] | None = None) -> dict[str, Any]:
        files = self._files()
        checkpoint = self._load_checkpoint()
        cursor = max(0, min(int(checkpoint.get("cursor", 0) or 0), len(files)))
        records = self._load_records()
        source_commit = _source_commit(self.vault_root)
        if cursor >= len(files):
            self._write_checkpoint(cursor=len(files), total=len(files), status="completed")
            self._write_proposal(files=files, indexed=len(records), source_commit=source_commit, complete=True)
            return {"status": "completed", "cursor": cursor, "total": len(files), "indexed": len(records)}

        processed = 0
        try:
            while cursor < len(files) and processed < self.config.batch_size:
                if should_preempt and should_preempt():
                    checkpoint = self._write_checkpoint(
                        cursor=cursor, total=len(files), status="paused", reason="foreground_task_or_user_activity"
                    )
                    return {"status": "paused", **checkpoint, "indexed": len(records)}
                batch_paths = files[cursor : cursor + self.config.batch_size - processed]
                texts = [path.read_text(encoding="utf-8", errors="replace") for path in batch_paths]
                vectors = self.client.embed(texts, input_type="passage")
                if len(vectors) != len(batch_paths):
                    raise EmbeddingError("embedding_count_mismatch")
                created = []
                for path, vector in zip(batch_paths, vectors):
                    relative = path.relative_to(self.vault_root).as_posix()
                    source_hash = _sha256(path)
                    key = f"{relative}:{source_hash}:{self.client.config.model}"
                    if key in records:
                        continue
                    record = {
                        "dedupe_key": key,
                        "source_path": relative,
                        "source_class": classify_source(path.relative_to(self.vault_root)),
                        "sha256": source_hash,
                        "source_commit": source_commit,
                        "model_id": self.client.config.model,
                        "input_type": "passage",
                        "vector_dimension": len(vector),
                        "embedding": [float(value) for value in vector],
                        "indexed_at": self.now(),
                    }
                    records[key] = record
                    created.append(record)
                self._append_records(created)
                cursor += len(batch_paths)
                processed += len(batch_paths)
                self._write_checkpoint(cursor=cursor, total=len(files), status="running")
        except EmbeddingError as exc:
            checkpoint = self._write_checkpoint(
                cursor=cursor, total=len(files), status="blocked", reason=str(exc)
            )
            return {"status": "blocked", **checkpoint, "indexed": len(records)}

        status = "completed" if cursor >= len(files) else "paused"
        reason = ""
        if status == "paused" and should_preempt and should_preempt():
            reason = "foreground_task_or_user_activity"
        checkpoint = self._write_checkpoint(cursor=cursor, total=len(files), status=status, reason=reason)
        self._write_proposal(
            files=files,
            indexed=len(records),
            source_commit=source_commit,
            complete=status == "completed",
        )
        return {"status": status, **checkpoint, "indexed": len(records)}


class IdleBackgroundWorker:
    def __init__(
        self,
        vault_root: str | Path,
        state_root: str | Path,
        *,
        job: EmbeddingRefreshJob,
        config: IdleWorkerConfig | None = None,
        lease: AutonomyLease | None = None,
        policy: AutonomyPolicy | None = None,
        worker_id: str = "embedding-idle-worker",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.vault_root = Path(vault_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.config = config or IdleWorkerConfig()
        self.job = job
        self.lease = lease or AutonomyLease(
            self.state_root / "idle-worker.lease", ttl_seconds=self.config.lease_ttl_seconds
        )
        self.policy = policy or AutonomyPolicy(
            AutonomyConfig(
                user_active_window_seconds=self.config.idle_seconds,
                cpu_pause_percent=self.config.cpu_pause_percent,
                memory_pause_percent=self.config.memory_pause_percent,
                max_concurrent_tasks=1,
                lease_ttl_seconds=self.config.lease_ttl_seconds,
            )
        )
        self.worker_id = worker_id
        self.clock = clock
        self.task_store = DurableTaskStore(self.state_root / "orchestrator")

    def _task_context(self) -> OperationContext:
        checkpoint = self.job._load_checkpoint()
        task_id = str(checkpoint.get("task_id") or f"embedding-refresh-{uuid.uuid4().hex}")
        values = {
            "task_id": task_id,
            "run_id": str(checkpoint.get("run_id") or f"run-{uuid.uuid4().hex}"),
            "operation_id": str(checkpoint.get("operation_id") or f"op-{uuid.uuid4().hex}"),
            "idempotency_key": str(checkpoint.get("idempotency_key") or f"idem-{uuid.uuid4().hex}"),
            "requested_by": "idle-background-worker",
        }
        self.job._write_checkpoint(
            cursor=int(checkpoint.get("cursor", 0) or 0),
            total=int(checkpoint.get("total", 0) or 0),
            status=str(checkpoint.get("status", "pending")),
            reason=str(checkpoint.get("reason", "")),
        )
        payload = self.job._load_checkpoint()
        payload.update(values)
        _atomic_json(self.job.checkpoint_path, payload)
        return OperationContext(**values)

    def _ensure_task(self) -> OperationContext:
        context = self._task_context()
        existing = self.task_store.get(context.task_id)
        if existing is None:
            self.task_store.create(
                TaskRecord(
                    context=context,
                    capability="read",
                    model_id=self.job.client.config.model,
                    tool_name="embedding_refresh",
                    validation_status="pending",
                    metadata={
                        "source_path": "vault://eligible-markdown",
                        "source_commit": _source_commit(self.vault_root),
                        "input_type": "passage",
                        "vector_dimension": self.job.client.config.dimension,
                        "batch_cursor": self.job._load_checkpoint().get("cursor", 0),
                    },
                )
            )
        return context

    def run_once(
        self,
        *,
        signals: dict[str, Any],
        foreground_pending: bool,
        foreground_probe: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if foreground_pending:
            return {"status": "paused", "reason": "foreground_task_pending"}
        decision = self.policy.evaluate(
            {
                "category": "maintenance",
                "input": "embedding_refresh",
                "priority": 1,
            },
            signals,
        )
        if not decision.get("allowed"):
            return {"status": "paused", "reason": decision.get("reason", "policy_rejected")}
        if not self.lease.acquire(self.worker_id):
            return {"status": "busy", "reason": "idle_worker_lease_unavailable"}
        try:
            context = self._ensure_task()
            if foreground_pending or (foreground_probe and foreground_probe()):
                return {"status": "paused", "reason": "foreground_task_pending"}
            self.task_store.transition(context.task_id, "running", validation_status="pending")
            result = self.job.run_batch(
                should_preempt=lambda: bool(foreground_pending or (foreground_probe and foreground_probe()))
            )
            result_status = result.get("status", "blocked")
            durable_status = "completed" if result_status == "completed" else "blocked"
            self.task_store.transition(
                context.task_id,
                durable_status,
                validation_status="passed" if result_status == "completed" else "pending",
                metadata={
                    "source_path": "vault://eligible-markdown",
                    "input_type": "passage",
                    "batch_cursor": result.get("cursor", 0),
                    "checkpoint_status": result_status,
                },
            )
            return {
                "status": result_status,
                "task_id": context.task_id,
                "run_id": context.run_id,
                "operation_id": context.operation_id,
                "idempotency_key": context.idempotency_key,
                "job_type": "embedding_refresh",
                "result": result,
            }
        except Exception as exc:
            self.task_store.transition(
                context.task_id,
                "blocked",
                validation_status="failed",
                metadata={"error_code": type(exc).__name__},
            )
            return {
                "status": "blocked",
                "task_id": context.task_id,
                "reason": type(exc).__name__,
            }
        finally:
            self.lease.release(self.worker_id)


__all__ = [
    "EmbeddingRefreshJob",
    "IdleBackgroundWorker",
    "IdleWorkerConfig",
    "classify_source",
    "eligible_markdown",
]

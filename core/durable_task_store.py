"""Small crash-recoverable task store with an append-only event log.

This is intentionally local and dependency-free. The event log is authoritative;
the JSON projection is rebuilt when it is missing or stale.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.orchestrator_types import TaskRecord, utc_now


class TaskStoreError(RuntimeError):
    pass


class DurableTaskStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.tasks_dir = self.root / "tasks"
        self.idempotency_dir = self.root / "idempotency"
        self.events_path = self.root / "events.jsonl"
        for path in (self.tasks_dir, self.idempotency_dir):
            path.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def append_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "occurred_at": utc_now(),
            **payload,
        }
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def create(self, record: TaskRecord) -> TaskRecord:
        existing = self.lookup_idempotency(record.context.idempotency_key)
        if existing and existing.get("operation_id") != record.context.operation_id:
            raise TaskStoreError("idempotency_conflict")
        self.append_event("task_created", record.as_dict())
        self._atomic_write(self.tasks_dir / f"{record.context.task_id}.json", record.as_dict())
        self._atomic_write(
            self.idempotency_dir / f"{record.context.idempotency_key}.json",
            record.as_dict(),
        )
        return record

    def lookup_idempotency(self, key: str) -> dict[str, Any] | None:
        path = self.idempotency_dir / f"{key}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskStoreError("idempotency_record_invalid") from exc

    def get(self, task_id: str) -> dict[str, Any] | None:
        path = self.tasks_dir / f"{task_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskStoreError("task_record_invalid") from exc

    def recover_stale_tasks(
        self,
        *,
        max_age_seconds: float = 900.0,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fail-closed stale active tasks after an interrupted process.

        Recovery never retries an MCP mutation. It marks only active execution
        states as blocked and requires reconciliation against the external
        project before a new operation identity can be created. Queued tasks
        are intentionally left alone because they may be waiting for a host.
        """
        active = {"claimed", "running", "validating"}
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        threshold = max(0.0, float(max_age_seconds))
        recovered: list[dict[str, Any]] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TaskStoreError("task_record_invalid") from exc
            if record.get("status") not in active:
                continue
            try:
                updated = datetime.fromisoformat(str(record.get("updated_at", "")).replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            age = max(0.0, (current_time - updated).total_seconds())
            if age <= threshold:
                continue
            metadata = dict(record.get("metadata") or {})
            metadata.update(
                {
                    "blocked_reason": "stale_task_recovery",
                    "failure_phase": "recovery",
                    "requires_reconciliation": True,
                    "auto_retry": False,
                    "stale_for_seconds": round(age, 3),
                }
            )
            recovered.append(
                self.transition(
                    str(record.get("task_id") or path.stem),
                    "blocked",
                    validation_status="failed",
                    metadata=metadata,
                )
            )
        return recovered

    def transition(self, task_id: str, status: str, **changes: Any) -> dict[str, Any]:
        current = self.get(task_id)
        if current is None:
            raise TaskStoreError("task_not_found")
        updated = {**current, **changes, "status": status, "updated_at": utc_now()}
        self.append_event("task_transition", updated)
        self._atomic_write(self.tasks_dir / f"{task_id}.json", updated)
        idempotency_key = updated.get("idempotency_key")
        if idempotency_key:
            self._atomic_write(self.idempotency_dir / f"{idempotency_key}.json", updated)
        return updated

    def rebuild_projection(self) -> dict[str, dict[str, Any]]:
        projection: dict[str, dict[str, Any]] = {}
        if not self.events_path.is_file():
            return projection
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            task_id = event.get("task_id")
            if task_id:
                projection[task_id] = {
                    key: value
                    for key, value in event.items()
                    if key not in {"event_type", "occurred_at"}
                }
        for task_id, record in projection.items():
            self._atomic_write(self.tasks_dir / f"{task_id}.json", record)
        return projection

"""Verify idle embedding recovery and preemption in an isolated disposable Vault.

This verifier never reads the user's Vault and never calls an external model.
It uses the production worker, durable task store, and lease implementation with
an in-memory fake embedding provider, then emits a machine-readable report.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from core.autonomy import AutonomyLease
from core.embedding_client import EmbeddingConfig
from core.idle_background_worker import (
    EmbeddingRefreshJob,
    IdleBackgroundWorker,
    IdleWorkerConfig,
)
from core.idle_readiness import build_readiness_report


class FakeEmbeddingClient:
    config = EmbeddingConfig(model="nvidia/nemotron-3-embed-1b", dimension=2048)

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        self.calls.append((list(texts), input_type))
        return [[float(index)] * self.config.dimension for index, _ in enumerate(texts, 1)]


def make_vault(root: Path) -> None:
    (root / "01-core").mkdir(parents=True)
    (root / "91 外部知識").mkdir(parents=True)
    (root / "ChatGPT 記憶資料庫").mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)
    (root / "01-core" / "a.md").write_text("A", encoding="utf-8")
    (root / "01-core" / "b.md").write_text("B", encoding="utf-8")
    (root / "91 外部知識" / "external.md").write_text("External", encoding="utf-8")
    (root / "ChatGPT 記憶資料庫" / "private.md").write_text("Private", encoding="utf-8")
    (root / "runtime" / "ignored.md").write_text("Runtime", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="white-studio-idle-e2e-") as temporary:
        root = Path(temporary)
        vault = root / "vault"
        state = root / "state" / "embedding-index"
        shared_autonomy = root / "shared-data" / "autonomy"
        make_vault(vault)
        config = IdleWorkerConfig(batch_size=1, transient_defer_seconds=1, transient_defer_limit=2)
        client = FakeEmbeddingClient()
        job = EmbeddingRefreshJob(vault, state, client=client, config=config)

        foreground = {"pending": False}

        def probe() -> bool:
            return foreground["pending"]

        original_embed = client.embed

        def embed_then_signal(texts: list[str], *, input_type: str) -> list[list[float]]:
            result = original_embed(texts, input_type=input_type)
            foreground["pending"] = True
            return result

        client.embed = embed_then_signal  # type: ignore[method-assign]
        first_worker = IdleBackgroundWorker(
            vault,
            state,
            job=job,
            config=config,
            autonomy_root=shared_autonomy,
            worker_id="e2e-first-worker",
        )
        paused = first_worker.run_once(
            signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
            foreground_pending=False,
            foreground_probe=probe,
        )
        checkpoint_after_pause = json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))

        client.embed = original_embed  # type: ignore[method-assign]
        recovery_worker = IdleBackgroundWorker(
            vault,
            state,
            job=EmbeddingRefreshJob(vault, state, client=client, config=config),
            config=config,
            autonomy_root=shared_autonomy,
            worker_id="e2e-recovery-worker",
        )
        recovery_results = []
        for _ in range(4):
            result = recovery_worker.run_once(
                signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
                foreground_pending=False,
            )
            recovery_results.append(result)
            if result.get("status") == "completed":
                break

        proposal = json.loads((state / "canonical-index-proposal.json").read_text(encoding="utf-8"))
        records = [
            json.loads(line)
            for line in (state / "embedding-index.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        held = AutonomyLease(shared_autonomy / "task.lease")
        assert held.acquire("e2e-foreground")
        try:
            busy = IdleBackgroundWorker(
                vault,
                state,
                job=EmbeddingRefreshJob(vault, state, client=client, config=config),
                config=config,
                autonomy_root=shared_autonomy,
                worker_id="e2e-background-contender",
            ).run_once(
                signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
                foreground_pending=False,
            )
        finally:
            held.release("e2e-foreground")

        readiness = build_readiness_report(state)
        checks = {
            "preemption_paused": paused.get("status") == "paused",
            "checkpoint_has_identity": all(
                checkpoint_after_pause.get(key)
                for key in ("task_id", "run_id", "operation_id", "idempotency_key")
            ),
            "recovery_completed": recovery_results[-1].get("status") == "completed",
            "proposal_requires_approval": proposal.get("promotion", {}).get("requires_human_approval") is True,
            "private_source_excluded": not any("private.md" in record["source_path"] for record in records),
            "lease_prevents_overlap": busy.get("status") == "busy",
            "readiness_checkpoint_observed": readiness["readiness"]["CHECKPOINT_RECOVERY_PASS"]["state"] == "observed",
            "readiness_preemption_observed": readiness["readiness"]["PREEMPTION_PASS"]["state"] == "observed",
            "canonical_promotion_disabled": readiness["overall"]["canonical_promotion_allowed"] is False,
        }
        report = {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "isolated": True,
            "external_api_called": False,
            "checks": checks,
            "records": len(records),
            "embedding_calls": len(client.calls),
            "readiness": readiness["readiness"],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only readiness projection for the idle embedding worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.idle_background_worker import IdleWorkerConfig

READINESS_KEYS = (
    "IDLE_ROUTER_READY",
    "EMBEDDING_BACKGROUND_WORKER_READY",
    "CHECKPOINT_RECOVERY_PASS",
    "PREEMPTION_PASS",
    "CANONICAL_INDEX_PROPOSAL_READY",
    "CANONICAL_INDEX_PROMOTION_PENDING_APPROVAL",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _entry(state: str, evidence: str) -> dict[str, str]:
    return {"state": state, "evidence": evidence}


def build_readiness_report(
    state_root: str | Path,
    *,
    config: IdleWorkerConfig | None = None,
    model_id: str = "nvidia/nemotron-3-embed-1b",
    vector_dimension: int = 2048,
) -> dict[str, Any]:
    """Build a truthful, read-only status report from local state only.

    The probe never treats a missing file as a pass and never infers a test
    result from configuration alone. Runtime behavior is marked as observed
    only when the worker left durable evidence for that behavior.
    """
    root = Path(state_root).resolve()
    worker_config = config or IdleWorkerConfig()
    checkpoint = _read_json(root / "checkpoint.json")
    proposal = _read_json(root / "canonical-index-proposal.json")

    report: dict[str, Any] = {
        "schema_version": 1,
        "state_root": str(root),
        "readiness": {},
    }
    report["readiness"]["IDLE_ROUTER_READY"] = _entry(
        "ready"
        if worker_config.idle_seconds >= 300
        and worker_config.batch_size > 0
        and worker_config.cpu_pause_percent <= 80
        and worker_config.memory_pause_percent <= 85
        else "blocked",
        "config:idle_seconds/batch_size/resource_thresholds",
    )
    report["readiness"]["EMBEDDING_BACKGROUND_WORKER_READY"] = _entry(
        "ready"
        if model_id.startswith("nvidia/nemotron-3-embed-") and int(vector_dimension) == 2048
        else "blocked",
        "config:model_id/vector_dimension",
    )

    checkpoint_identity = (
        checkpoint
        and checkpoint.get("schema_version") == 1
        and checkpoint.get("job_type") == "embedding_refresh"
        and checkpoint.get("task_id")
        and checkpoint.get("run_id")
        and checkpoint.get("operation_id")
        and checkpoint.get("idempotency_key")
        and checkpoint.get("source_manifest_sha256")
        and checkpoint.get("source_commit")
    )
    report["readiness"]["CHECKPOINT_RECOVERY_PASS"] = _entry(
        "observed" if checkpoint_identity else "pending_evidence",
        "checkpoint.json:identity+source-lock" if checkpoint_identity else "checkpoint.json:missing_or_incomplete",
    )
    preempted = bool(
        checkpoint
        and (
            checkpoint.get("preemption_observed") is True
            or (
                checkpoint.get("status") == "paused"
                and str(checkpoint.get("reason") or "").strip()
            )
        )
    )
    report["readiness"]["PREEMPTION_PASS"] = _entry(
        "observed" if preempted else "pending_evidence",
        "checkpoint.json:preemption_observed" if preempted else "no_durable_pause_observed",
    )

    proposal_ready = bool(
        proposal
        and proposal.get("schema_version") == 1
        and proposal.get("job_type") == "embedding_refresh"
        and proposal.get("status") == "canonical-index-promotion-pending-approval"
        and proposal.get("source_commit")
        and proposal.get("source_manifest_sha256")
        and proposal.get("model_id")
        and proposal.get("vector_dimension") == 2048
    )
    report["readiness"]["CANONICAL_INDEX_PROPOSAL_READY"] = _entry(
        "ready" if proposal_ready else "pending_evidence",
        "canonical-index-proposal.json:validated_shape" if proposal_ready else "proposal_missing_or_incomplete",
    )
    report["readiness"]["CANONICAL_INDEX_PROMOTION_PENDING_APPROVAL"] = _entry(
        "pending_approval" if proposal_ready else "not_ready",
        "canonical promotion remains disabled until separate approval"
        if proposal_ready
        else "no validated proposal",
    )
    report["overall"] = {
        "local_worker_configured": report["readiness"]["IDLE_ROUTER_READY"]["state"] == "ready"
        and report["readiness"]["EMBEDDING_BACKGROUND_WORKER_READY"]["state"] == "ready",
        "canonical_promotion_allowed": False,
        "requires_test_evidence": [
            key
            for key in ("CHECKPOINT_RECOVERY_PASS", "PREEMPTION_PASS")
            if report["readiness"][key]["state"] != "observed"
        ],
    }
    return report


__all__ = ["READINESS_KEYS", "build_readiness_report"]

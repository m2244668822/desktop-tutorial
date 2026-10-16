"""Shared identity and task types for the local White Studio orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class OperationContext:
    task_id: str
    run_id: str
    operation_id: str
    idempotency_key: str
    requested_by: str = "orchestrator"

    @classmethod
    def create(cls, task_id: str, *, requested_by: str = "orchestrator") -> "OperationContext":
        return cls(
            task_id=task_id,
            run_id=f"run-{uuid4().hex}",
            operation_id=f"op-{uuid4().hex}",
            idempotency_key=f"idem-{uuid4().hex}",
            requested_by=requested_by,
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "operation_id": self.operation_id,
            "idempotency_key": self.idempotency_key,
            "requested_by": self.requested_by,
        }


@dataclass
class TaskRecord:
    context: OperationContext
    status: str = "queued"
    capability: str = "read"
    model_id: str | None = None
    mcp_server: str | None = None
    tool_name: str | None = None
    project_id: str | None = None
    project_fingerprint: str | None = None
    before_state_hash: str | None = None
    after_state_hash: str | None = None
    validation_status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, Any]:
        result = {
            **self.context.as_dict(),
            "status": self.status,
            "capability": self.capability,
            "model_id": self.model_id,
            "mcp_server": self.mcp_server,
            "tool_name": self.tool_name,
            "project_id": self.project_id,
            "project_fingerprint": self.project_fingerprint,
            "before_state_hash": self.before_state_hash,
            "after_state_hash": self.after_state_hash,
            "validation_status": self.validation_status,
            "metadata": self.metadata,
            "updated_at": self.updated_at,
        }
        return result

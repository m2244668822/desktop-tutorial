"""Single-process orchestration primitives for bounded MCP operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Protocol

from core.durable_task_store import DurableTaskStore
from core.orchestrator_types import OperationContext, TaskRecord
from core.policy_engine import PolicyEngine


class McpClient(Protocol):
    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


def state_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare_state(before: Any, after: Any) -> dict[str, Any]:
    before_hash = state_hash(before)
    after_hash = state_hash(after)
    return {
        "equal": before_hash == after_hash,
        "before_state_hash": before_hash,
        "after_state_hash": after_hash,
    }


class Orchestrator:
    def __init__(self, store: DurableTaskStore, policy: PolicyEngine | None = None):
        self.store = store
        self.policy = policy or PolicyEngine()

    def run_mutation(
        self,
        *,
        context: OperationContext,
        client: McpClient,
        tool_name: str,
        arguments: dict[str, Any],
        project_id: str,
        project_fingerprint: str,
        disposable_project: bool = True,
        target_confirmed: bool = False,
        capability: str = "disposable_write",
        undo_tool: str | None = None,
        undo_arguments: dict[str, Any] | None = None,
        result_validator: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        self.policy.authorize(
            capability=capability,
            project_id=project_id,
            project_fingerprint=project_fingerprint,
            target_confirmed=target_confirmed,
            disposable_project=disposable_project,
        )
        record = TaskRecord(
            context=context,
            status="queued",
            capability=capability,
            mcp_server="filmcraft",
            tool_name=tool_name,
            project_id=project_id,
            project_fingerprint=project_fingerprint,
        )
        existing = self.store.lookup_idempotency(context.idempotency_key)
        if existing:
            return {"record": existing, "result": {"idempotent_replay": True}}
        self.store.create(record)
        self.store.transition(context.task_id, "running")

        before = client.call("state_snapshot", {})
        before_hash = state_hash(before)
        self.store.transition(context.task_id, "running", before_state_hash=before_hash)
        result = client.call(tool_name, arguments)
        after = client.call("state_snapshot", {})
        after_hash = state_hash(after)
        self.store.transition(context.task_id, "running", after_state_hash=after_hash)

        if result_validator and not result_validator(before, after):
            self.store.transition(context.task_id, "failed", validation_status="failed")
            raise RuntimeError("readback_failed")

        if undo_tool:
            undo_result = client.call(undo_tool, undo_arguments or {})
            restored = client.call("state_snapshot", {})
            comparison = compare_state(before, restored)
            restored_hash = comparison["after_state_hash"]
            if not comparison["equal"]:
                self.store.transition(context.task_id, "failed", validation_status="failed")
                raise RuntimeError("state_mismatch")
            result = {
                "mutation": result,
                "undo": undo_result,
                "restored_state_hash": restored_hash,
                "state_compare": comparison,
            }

        final = self.store.transition(
            context.task_id,
            "completed",
            after_state_hash=after_hash,
            validation_status="passed",
        )
        return {"record": final, "result": result}

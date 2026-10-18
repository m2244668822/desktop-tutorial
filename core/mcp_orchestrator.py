"""Single-process orchestration primitives for bounded MCP operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Protocol

from core.chat_gateway import ChatGatewayBlocked, ChatRequest
from core.durable_task_store import DurableTaskStore
from core.orchestrator_types import OperationContext, TaskRecord
from core.policy_engine import PolicyDenied, PolicyEngine


class McpClient(Protocol):
    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


READ_TOOL_NAMES = frozenset({
    "project_inspect",
    "sequence_inspect",
    "marker_list",
    "state_snapshot",
})
WRITE_TOOL_NAMES = frozenset({"markers_add", "command_run", "edit_undo"})
LOCAL_VALIDATOR_NAMES = frozenset({"state_compare"})
READ_RETRYABLE_PHASES = frozenset({"read", "snapshot_before", "snapshot_after", "snapshot_restored"})


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
    def __init__(
        self,
        store: DurableTaskStore,
        policy: PolicyEngine | None = None,
        *,
        stale_after_seconds: float = 1800.0,
    ):
        self.store = store
        self.policy = policy or PolicyEngine()
        self.recovered_stale_tasks = self.store.recover_stale_tasks(
            max_age_seconds=stale_after_seconds
        )

    def recover_stale_tasks(self, *, max_age_seconds: float = 900.0, now=None) -> list[dict[str, Any]]:
        """Mark interrupted active tasks blocked; never replay a mutation."""
        return self.store.recover_stale_tasks(max_age_seconds=max_age_seconds, now=now)

    def _call_mcp(
        self,
        *,
        context: OperationContext,
        client: McpClient,
        tool_name: str,
        arguments: dict[str, Any],
        phase: str,
    ) -> dict[str, Any]:
        """Call MCP with hash-only audit events and no raw payload persistence."""
        attempts = 2 if phase in READ_RETRYABLE_PHASES else 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            audit = {
                **context.as_dict(),
                "mcp_server": "filmcraft",
                "tool_name": tool_name,
                "phase": phase,
                "attempt": attempt,
                "arguments_hash": state_hash(arguments),
            }
            self.store.append_event("mcp_call_started", audit)
            try:
                contextual_call = getattr(client, "call_with_context", None)
                if callable(contextual_call):
                    result = contextual_call(
                        context=context.as_dict(),
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                else:
                    result = client.call(tool_name, arguments)
            except Exception as exc:
                last_error = exc
                self.store.append_event(
                    "mcp_call_finished",
                    {
                        **audit,
                        "success": False,
                        "error_code": getattr(exc, "code", None) or exc.__class__.__name__,
                    },
                )
                if attempt < attempts:
                    continue
                raise
            self.store.append_event(
                "mcp_call_finished",
                {
                    **audit,
                    "success": not (isinstance(result, dict) and result.get("success") is False),
                    "response_hash": state_hash(result),
                },
            )
            return result
        raise last_error or RuntimeError("mcp_call_failed")

    def _block_mutation(self, context: OperationContext, error: Exception, phase: str) -> dict[str, Any]:
        """Persist a failed MCP mutation without converting it into success."""
        reason = getattr(error, "code", None) or str(error) or error.__class__.__name__
        current = self.store.get(context.task_id) or {}
        metadata = dict(current.get("metadata") or {})
        metadata.update(
            {
                "blocked_reason": reason,
                "failure_phase": phase,
                "requires_reconciliation": phase in {"mutation", "readback", "undo"},
            }
        )
        blocked = self.store.transition(
            context.task_id,
            "blocked",
            validation_status="failed",
            metadata=metadata,
        )
        return {"record": blocked, "result": None, "error": reason}

    def run_chat(
        self,
        *,
        context: OperationContext,
        gateway,
        request: ChatRequest,
        previous_response=None,
        continuation_user_content: str | None = None,
    ) -> dict[str, Any]:
        """Persist one chat turn without granting it MCP mutation access.

        A continuation is explicitly pinned to the previous response model by
        ``ChatModelGateway.continue_chat``. It is a new durable turn, so its
        task/run identity may differ from the previous response identity.
        """
        if (request.task_id, request.run_id) != (context.task_id, context.run_id):
            raise ChatGatewayBlocked("chat_identity_mismatch")

        existing = self.store.lookup_idempotency(context.idempotency_key)
        if existing:
            return {"record": existing, "response": None, "idempotent_replay": True}

        record = TaskRecord(
            context=context,
            status="queued",
            capability="read",
            tool_name="chat.complete",
            metadata={"privacy_class": request.privacy_class},
        )
        self.store.create(record)
        self.store.transition(context.task_id, "running")

        try:
            if previous_response is not None:
                if continuation_user_content is None:
                    raise ChatGatewayBlocked("continuation_user_content_missing")
                response = gateway.continue_chat(
                    request,
                    previous_response,
                    continuation_user_content,
                )
            else:
                response = gateway.complete(request)
            if (
                response.status != "complete"
                or not response.content.strip()
                or response.task_id != context.task_id
                or response.run_id != context.run_id
            ):
                raise ChatGatewayBlocked("chat_response_invalid")
        except ChatGatewayBlocked as exc:
            blocked = self.store.transition(
                context.task_id,
                "blocked",
                validation_status="failed",
                metadata={
                    "privacy_class": request.privacy_class,
                    "blocked_reason": str(exc),
                },
            )
            return {"record": blocked, "response": None, "error": str(exc)}
        except Exception:
            blocked = self.store.transition(
                context.task_id,
                "blocked",
                validation_status="failed",
                metadata={
                    "privacy_class": request.privacy_class,
                    "blocked_reason": "chat_runtime_error",
                },
            )
            return {"record": blocked, "response": None, "error": "chat_runtime_error"}

        completed = self.store.transition(
            context.task_id,
            "completed",
            model_id=response.model_id,
            validation_status="passed",
            metadata={
                "privacy_class": request.privacy_class,
                "provider": response.provider,
                "attempted_models": list(response.attempted_models),
                "fallback_used": response.fallback_used,
            },
        )
        return {"record": completed, "response": response}

    def execute_tool_proposal(
        self,
        *,
        context: OperationContext,
        client: McpClient,
        tool_name: str,
        arguments: dict[str, Any],
        capability: str | None = None,
        project_id: str | None = None,
        project_fingerprint: str | None = None,
        disposable_project: bool = False,
        target_confirmed: bool = False,
        undo_tool: str | None = None,
        undo_arguments: dict[str, Any] | None = None,
        result_validator: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """Route a model proposal through classification and policy gates."""
        if tool_name in READ_TOOL_NAMES:
            return self.run_read(
                context=context,
                client=client,
                tool_name=tool_name,
                arguments=arguments,
            )
        if tool_name in LOCAL_VALIDATOR_NAMES:
            if "before" not in arguments or "after" not in arguments:
                raise PolicyDenied("state_compare_inputs_required")
            return self.run_state_compare(
                context=context,
                before=arguments["before"],
                after=arguments["after"],
            )
        if tool_name in WRITE_TOOL_NAMES:
            if capability not in {"disposable_write", "real_write"}:
                raise PolicyDenied("tool_proposal_write_authorization_required")
            return self.run_mutation(
                context=context,
                client=client,
                tool_name=tool_name,
                arguments=arguments,
                project_id=project_id or "",
                project_fingerprint=project_fingerprint or "",
                disposable_project=disposable_project,
                target_confirmed=target_confirmed,
                capability=capability,
                undo_tool=undo_tool,
                undo_arguments=undo_arguments,
                result_validator=result_validator,
            )
        raise PolicyDenied("tool_proposal_unknown")

    def run_state_compare(
        self,
        *,
        context: OperationContext,
        before: Any,
        after: Any,
    ) -> dict[str, Any]:
        """Persist a local comparison without sending a fake MCP tool call."""
        existing = self.store.lookup_idempotency(context.idempotency_key)
        if existing:
            if existing.get("status") == "completed":
                return {
                    "record": existing,
                    "result": {"idempotent_replay": True, "status": "completed", "read_only": True},
                }
            return {
                "record": existing,
                "result": None,
                "error": "idempotent_replay_not_completed",
                "idempotent_replay": True,
            }
        record = TaskRecord(
            context=context,
            status="queued",
            capability="read",
            mcp_server="orchestrator",
            tool_name="state_compare",
            metadata={"read_only": True},
        )
        self.store.create(record)
        self.store.transition(context.task_id, "running")
        try:
            comparison = compare_state(before, after)
            self.store.append_event(
                "state_compare_finished",
                {
                    **context.as_dict(),
                    "tool_name": "state_compare",
                    "before_state_hash": comparison["before_state_hash"],
                    "after_state_hash": comparison["after_state_hash"],
                    "equal": comparison["equal"],
                },
            )
            completed = self.store.transition(
                context.task_id,
                "completed",
                before_state_hash=comparison["before_state_hash"],
                after_state_hash=comparison["after_state_hash"],
                validation_status="passed",
                metadata={"read_only": True, "equal": comparison["equal"]},
            )
            return {
                "record": completed,
                "result": {
                    "success": True,
                    "read_only": True,
                    **context.as_dict(),
                    "state_compare": comparison,
                },
            }
        except Exception as exc:
            return self._block_mutation(context, exc, "validation")

    def run_read(
        self,
        *,
        context: OperationContext,
        client: McpClient,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Run one allowlisted read tool through durable state and audit."""
        if tool_name not in READ_TOOL_NAMES:
            raise PolicyDenied("read_tool_required")
        existing = self.store.lookup_idempotency(context.idempotency_key)
        if existing:
            if existing.get("status") == "completed":
                return {
                    "record": existing,
                    "result": {"idempotent_replay": True, "status": "completed", "read_only": True},
                }
            return {
                "record": existing,
                "result": None,
                "error": "idempotent_replay_not_completed",
                "idempotent_replay": True,
            }
        record = TaskRecord(
            context=context,
            status="queued",
            capability="read",
            mcp_server="filmcraft",
            tool_name=tool_name,
            metadata={"read_only": True},
        )
        self.store.create(record)
        self.store.transition(context.task_id, "running")
        try:
            raw_result = self._call_mcp(
                context=context,
                client=client,
                tool_name=tool_name,
                arguments=arguments,
                phase="read",
            )
            if isinstance(raw_result, dict) and raw_result.get("success") is False:
                raise RuntimeError("mcp_result_not_success")
            payload = dict(raw_result) if isinstance(raw_result, dict) else {"value": raw_result}
            payload.update(
                {
                    "success": True,
                    "read_only": True,
                    "task_id": context.task_id,
                    "run_id": context.run_id,
                    "operation_id": context.operation_id,
                    "source": payload.get("source") or "filmcraft-adapter",
                    "runtime_version": payload.get("runtime_version") or "unknown",
                }
            )
            completed = self.store.transition(
                context.task_id,
                "completed",
                validation_status="passed",
                metadata={"read_only": True, "response_hash": state_hash(raw_result)},
            )
            return {"record": completed, "result": payload}
        except Exception as exc:
            return self._block_mutation(context, exc, "read")

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
        if tool_name in READ_TOOL_NAMES:
            raise PolicyDenied("read_tool_requires_read_path")
        if tool_name not in WRITE_TOOL_NAMES:
            raise PolicyDenied("mutation_tool_unknown")
        if capability not in {"disposable_write", "real_write"}:
            raise PolicyDenied("mutation_capability_required")
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
            if existing.get("status") == "completed":
                return {
                    "record": existing,
                    "result": {"idempotent_replay": True, "status": "completed"},
                }
            return {
                "record": existing,
                "result": None,
                "error": "idempotent_replay_not_completed",
                "idempotent_replay": True,
            }
        self.store.create(record)
        self.store.transition(context.task_id, "running")

        try:
            before = self._call_mcp(
                context=context,
                client=client,
                tool_name="state_snapshot",
                arguments={},
                phase="snapshot_before",
            )
            before_hash = state_hash(before)
            self.store.transition(context.task_id, "running", before_state_hash=before_hash)
            result = self._call_mcp(
                context=context,
                client=client,
                tool_name=tool_name,
                arguments=arguments,
                phase="mutation",
            )
            if isinstance(result, dict) and result.get("success") is False:
                raise RuntimeError("mcp_result_not_success")
            after = self._call_mcp(
                context=context,
                client=client,
                tool_name="state_snapshot",
                arguments={},
                phase="snapshot_after",
            )
            after_hash = state_hash(after)
            self.store.transition(context.task_id, "running", after_state_hash=after_hash)

            if result_validator and not result_validator(before, after):
                raise RuntimeError("readback_failed")

            if undo_tool:
                undo_result = self._call_mcp(
                    context=context,
                    client=client,
                    tool_name=undo_tool,
                    arguments=undo_arguments or {},
                    phase="undo",
                )
                restored = self._call_mcp(
                    context=context,
                    client=client,
                    tool_name="state_snapshot",
                    arguments={},
                    phase="snapshot_restored",
                )
                comparison = compare_state(before, restored)
                restored_hash = comparison["after_state_hash"]
                if not comparison["equal"]:
                    raise RuntimeError("state_mismatch")
                result = {
                    "mutation": result,
                    "undo": undo_result,
                    "restored_state_hash": restored_hash,
                    "state_compare": comparison,
                }
            payload = dict(result) if isinstance(result, dict) else {"value": result}
            nested = payload.get("mutation") if isinstance(payload.get("mutation"), dict) else payload
            payload.update(
                {
                    "success": True,
                    "task_id": context.task_id,
                    "run_id": context.run_id,
                    "operation_id": context.operation_id,
                    "project_id": project_id,
                    "before_state_hash": before_hash,
                    "after_state_hash": after_hash,
                    "undo_available": bool(undo_tool),
                    "source": nested.get("source") or f"{record.mcp_server}-adapter",
                    "runtime_version": nested.get("runtime_version") or "unknown",
                }
            )
            result = payload
        except Exception as exc:
            phase = "readback"
            reason = getattr(exc, "code", None) or str(exc)
            if reason in {"readback_failed", "state_mismatch"}:
                phase = "validation"
            elif undo_tool and "undo" in reason:
                phase = "undo"
            elif "snapshot" in reason:
                phase = "readback"
            else:
                phase = "mutation"
            return self._block_mutation(context, exc, phase)

        final = self.store.transition(
            context.task_id,
            "completed",
            after_state_hash=after_hash,
            validation_status="passed",
        )
        return {"record": final, "result": result}

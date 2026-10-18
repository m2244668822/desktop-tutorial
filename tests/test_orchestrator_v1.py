import json
import queue
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.durable_task_store import DurableTaskStore, TaskStoreError
from core.chat_gateway import ChatGatewayBlocked, ChatRequest, ChatResponse
from core.filmcraft_adapter import FilmCraftMcpAdapter, JsonlMcpProcess
from core.mcp_orchestrator import Orchestrator, compare_state
from core.model_router import ModelCallError, ModelProvider, ModelRouter, ModelUnavailable, RetryPolicy
from core.orchestrator_types import OperationContext, TaskRecord
from core.policy_engine import PolicyEngine, PolicyDenied


class FakeMcpClient:
    def __init__(self):
        self.state = {"markers": ["original"]}
        self.calls = []

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "state_snapshot":
            return json.loads(json.dumps(self.state))
        if tool_name == "markers_add":
            self.state["markers"].append(arguments["name"])
            return {"success": True}
        if tool_name == "edit_undo":
            self.state["markers"] = ["original"]
            return {"undone": "Add Marker"}
        raise AssertionError(tool_name)


class FailingMcpClient(FakeMcpClient):
    def __init__(self, failure_phase="mutation"):
        super().__init__()
        self.failure_phase = failure_phase

    def call(self, tool_name, arguments):
        if tool_name == "markers_add" and self.failure_phase == "mutation":
            raise RuntimeError("mcp_timeout")
        if tool_name == "edit_undo" and self.failure_phase == "undo":
            raise RuntimeError("undo_timeout")
        return super().call(tool_name, arguments)


class UnsuccessfulMcpClient(FakeMcpClient):
    def call(self, tool_name, arguments):
        if tool_name == "markers_add":
            self.calls.append((tool_name, arguments))
            return {"success": False, "error": "rejected"}
        return super().call(tool_name, arguments)


class ReadMcpClient:
    def __init__(self):
        self.calls = []

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name in {"project_inspect", "sequence_inspect", "marker_list", "state_snapshot"}:
            return {"success": True, "project": {"id": "demo"}}
        raise AssertionError(tool_name)


class TransientReadMcpClient(ReadMcpClient):
    def __init__(self):
        super().__init__()
        self.fail_once = True

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "project_inspect" and self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary_read_timeout")
        return {"success": True, "project": {"id": "demo"}}


class FakeFilmCraftTransport:
    def __init__(self):
        self.requests = []

    def request(self, method, params):
        self.requests.append((method, params))
        if method == "tools/list":
            return {
                "tools": [
                    {"name": "doc_inspect", "inputSchema": {"type": "object"}},
                    {"name": "project_inspect", "inputSchema": {"type": "object"}},
                    {"name": "sequence_inspect", "inputSchema": {"type": "object"}},
                    {"name": "command_run", "inputSchema": {"type": "object"}},
                ]
            }
        if method == "tools/call":
            name = params["name"]
            if name == "doc_inspect":
                text = json.dumps({"sequence": {"markers": []}})
            else:
                text = json.dumps({"success": True})
            return {"content": [{"type": "text", "text": text}]}
        raise AssertionError(method)


class MissingFilmCraftToolTransport(FakeFilmCraftTransport):
    def request(self, method, params):
        if method == "tools/list":
            self.requests.append((method, params))
            return {"tools": [{"name": "doc_inspect", "inputSchema": {"type": "object"}}]}
        return super().request(method, params)


class MalformedFilmCraftSchemaTransport(FakeFilmCraftTransport):
    def __init__(self, duplicate=False):
        super().__init__()
        self.duplicate = duplicate

    def request(self, method, params):
        if method == "tools/list":
            self.requests.append((method, params))
            tools = [{"name": "command_run", "inputSchema": {"type": "object"}}]
            if self.duplicate:
                tools.append({"name": "command_run", "inputSchema": {"type": "object"}})
            else:
                tools.append({"name": "doc_inspect"})
            return {"tools": tools}
        return super().request(method, params)


class RequiredArgumentFilmCraftTransport(FakeFilmCraftTransport):
    def request(self, method, params):
        if method == "tools/list":
            self.requests.append((method, params))
            return {
                "tools": [
                    {
                        "name": "project_inspect",
                        "inputSchema": {
                            "type": "object",
                            "required": ["project_id"],
                            "properties": {"project_id": {"type": "string"}},
                        },
                    }
                ]
            }
        return super().request(method, params)


class FakeChatGateway:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response

    def continue_chat(self, request, previous_response, user_content):
        self.requests.append((request, previous_response, user_content))
        if self.error:
            raise self.error
        return ChatResponse(
            status=self.response.status,
            content=self.response.content,
            provider=self.response.provider,
            model_id=self.response.model_id,
            task_id=request.task_id,
            run_id=request.run_id,
            attempted_models=self.response.attempted_models,
            fallback_used=self.response.fallback_used,
            reasoning_details=self.response.reasoning_details,
            tool_calls=self.response.tool_calls,
        )


class OrchestratorV1Tests(unittest.TestCase):
    def test_jsonl_transport_matches_out_of_order_responses_by_id(self):
        client = object.__new__(JsonlMcpProcess)
        client.timeout = 0.1
        client._responses = queue.Queue()
        client._unmatched = {}
        client._response_lock = threading.Lock()
        client._responses.put({"jsonrpc": "2.0", "id": 2, "result": {"value": "second"}})
        client._responses.put({"jsonrpc": "2.0", "id": 1, "result": {"value": "first"}})

        self.assertEqual({"value": "first"}, client._response_for(1)["result"])
        self.assertEqual({"value": "second"}, client._response_for(2)["result"])

    def test_orchestrator_passes_identity_to_contextual_mcp_adapter(self):
        transport = FakeFilmCraftTransport()
        adapter = FilmCraftMcpAdapter(transport, project_id="demo", project_fingerprint="sha256:demo")
        with tempfile.TemporaryDirectory() as tmp:
            context = OperationContext.create("contextual-read")
            result = Orchestrator(DurableTaskStore(tmp)).run_read(
                context=context,
                client=adapter,
                tool_name="project_inspect",
                arguments={},
            )
            self.assertEqual("completed", result["record"]["status"])
            self.assertEqual(context.task_id, adapter.last_call_context["task_id"])
            self.assertEqual(context.operation_id, adapter.last_call_context["operation_id"])
            self.assertNotIn("_meta", transport.requests[-1][1])

    def test_orchestrator_persists_chat_completion_without_mcp_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = OperationContext.create("chat-1", requested_by="codex")
            response = ChatResponse(
                status="complete",
                content="draft reply",
                provider="openrouter",
                model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
                task_id=context.task_id,
                run_id=context.run_id,
                attempted_models=("nvidia/nemotron-3-ultra-550b-a55b:free",),
                fallback_used=False,
            )
            gateway = FakeChatGateway(response=response)
            result = Orchestrator(DurableTaskStore(tmp)).run_chat(
                context=context,
                gateway=gateway,
                request=ChatRequest(
                    task_id=context.task_id,
                    run_id=context.run_id,
                    messages=[{"role": "user", "content": "write copy"}],
                    privacy_class="cloud",
                ),
            )

            self.assertEqual("completed", result["record"]["status"])
            self.assertEqual("passed", result["record"]["validation_status"])
            self.assertEqual("nvidia/nemotron-3-ultra-550b-a55b:free", result["record"]["model_id"])
            self.assertEqual("draft reply", result["response"].content)
            self.assertEqual("chat.complete", result["record"]["tool_name"])
            self.assertEqual("read", result["record"]["capability"])

    def test_orchestrator_blocks_chat_without_fake_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = OperationContext.create("chat-blocked")
            gateway = FakeChatGateway(error=ChatGatewayBlocked("chat_providers_exhausted"))
            result = Orchestrator(DurableTaskStore(tmp)).run_chat(
                context=context,
                gateway=gateway,
                request=ChatRequest(
                    task_id=context.task_id,
                    run_id=context.run_id,
                    messages=[{"role": "user", "content": "write copy"}],
                ),
            )

            self.assertEqual("blocked", result["record"]["status"])
            self.assertEqual("failed", result["record"]["validation_status"])
            self.assertEqual("chat_providers_exhausted", result["error"])

    def test_orchestrator_persists_same_model_continuation_as_new_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = ChatResponse(
                status="complete",
                content="first",
                provider="openrouter",
                model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
                task_id="old-task",
                run_id="old-run",
                attempted_models=("nvidia/nemotron-3-ultra-550b-a55b:free",),
                fallback_used=False,
                reasoning_details=[{"type": "reasoning.summary", "data": "opaque"}],
            )
            current = OperationContext.create("new-turn", requested_by="desktop-bridge")
            gateway = FakeChatGateway(response=previous)
            result = Orchestrator(DurableTaskStore(tmp)).run_chat(
                context=current,
                gateway=gateway,
                request=ChatRequest(
                    task_id=current.task_id,
                    run_id=current.run_id,
                    messages=[{"role": "user", "content": "first"}],
                    privacy_class="cloud",
                ),
                previous_response=previous,
                continuation_user_content="follow up",
            )

            self.assertEqual("completed", result["record"]["status"])
            self.assertEqual("follow up", gateway.requests[0][2])
            self.assertEqual(current.task_id, result["response"].task_id)

    def test_store_survives_projection_rebuild_and_rejects_idempotency_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DurableTaskStore(tmp)
            first = TaskRecord(OperationContext.create("task-1"))
            store.create(first)
            store.transition("task-1", "running")
            Path(tmp, "tasks", "task-1.json").unlink()
            rebuilt = store.rebuild_projection()
            self.assertEqual("running", rebuilt["task-1"]["status"])
            second = TaskRecord(OperationContext.create("task-2"))
            second.context = second.context.__class__(
                task_id="task-2",
                run_id=second.context.run_id,
                operation_id=second.context.operation_id,
                idempotency_key=first.context.idempotency_key,
            )
            with self.assertRaises(TaskStoreError):
                store.create(second)

    def test_stale_active_task_is_blocked_without_automatic_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DurableTaskStore(tmp)
            context = OperationContext.create("stale-task")
            store.create(TaskRecord(context))
            store.transition("stale-task", "running")
            record_path = Path(tmp, "tasks", "stale-task.json")
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["updated_at"] = "2026-10-17T00:00:00+00:00"
            record_path.write_text(json.dumps(record), encoding="utf-8")

            recovered = store.recover_stale_tasks(
                max_age_seconds=900,
                now=datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(1, len(recovered))
            self.assertEqual("blocked", recovered[0]["status"])
            self.assertEqual("stale_task_recovery", recovered[0]["metadata"]["blocked_reason"])
            self.assertTrue(recovered[0]["metadata"]["requires_reconciliation"])
            self.assertFalse(recovered[0]["metadata"]["auto_retry"])
            self.assertEqual(
                [],
                store.recover_stale_tasks(
                    max_age_seconds=900,
                    now=datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc),
                ),
            )

    def test_orchestrator_startup_runs_stale_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DurableTaskStore(tmp)
            context = OperationContext.create("startup-stale-task")
            store.create(TaskRecord(context))
            store.transition(context.task_id, "running")
            record_path = Path(tmp, "tasks", f"{context.task_id}.json")
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["updated_at"] = "2026-10-17T00:00:00+00:00"
            record_path.write_text(json.dumps(record), encoding="utf-8")

            orchestrator = Orchestrator(store, stale_after_seconds=1)
            self.assertEqual(1, len(orchestrator.recovered_stale_tasks))
            self.assertEqual("blocked", store.get(context.task_id)["status"])

    def test_policy_fails_closed_for_ambiguous_or_real_targets(self):
        policy = PolicyEngine()
        with self.assertRaises(PolicyDenied):
            policy.authorize(capability="disposable_write", project_id="current", project_fingerprint="x", disposable_project=True)
        with self.assertRaises(PolicyDenied):
            policy.authorize(capability="real_write", project_id="p", project_fingerprint="x")
        self.assertTrue(policy.authorize(capability="read").allowed)

    def test_mutation_rejects_read_capability_before_mcp_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMcpClient()
            with self.assertRaisesRegex(PolicyDenied, "mutation_capability_required"):
                Orchestrator(DurableTaskStore(tmp)).run_mutation(
                    context=OperationContext.create("mutation-read-bypass"),
                    client=client,
                    tool_name="markers_add",
                    arguments={"name": "must-not-run"},
                    project_id="demo",
                    project_fingerprint="sha256:demo",
                    capability="read",
                )
            self.assertEqual([], client.calls)

    def test_read_path_is_durable_and_rejects_write_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ReadMcpClient()
            context = OperationContext.create("filmcraft-read")
            result = Orchestrator(DurableTaskStore(tmp)).run_read(
                context=context,
                client=client,
                tool_name="project_inspect",
                arguments={},
            )

            self.assertEqual("completed", result["record"]["status"])
            self.assertTrue(result["result"]["success"])
            self.assertTrue(result["result"]["read_only"])
            self.assertEqual(context.operation_id, result["result"]["operation_id"])

            with self.assertRaisesRegex(PolicyDenied, "read_tool_required"):
                Orchestrator(DurableTaskStore(tmp)).run_read(
                    context=OperationContext.create("filmcraft-read-write-bypass"),
                    client=client,
                    tool_name="markers_add",
                    arguments={"name": "must-not-run"},
                )

    def test_read_transport_failure_retries_once_and_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TransientReadMcpClient()
            result = Orchestrator(DurableTaskStore(tmp)).run_read(
                context=OperationContext.create("filmcraft-read-retry"),
                client=client,
                tool_name="project_inspect",
                arguments={},
            )
            self.assertEqual("completed", result["record"]["status"])
            self.assertEqual(2, len(client.calls))

    def test_tool_proposal_routes_read_and_requires_write_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ReadMcpClient()
            orchestrator = Orchestrator(DurableTaskStore(tmp))
            read_result = orchestrator.execute_tool_proposal(
                context=OperationContext.create("proposal-read"),
                client=client,
                tool_name="project_inspect",
                arguments={},
            )
            self.assertEqual("completed", read_result["record"]["status"])
            self.assertTrue(read_result["result"]["read_only"])

            with self.assertRaisesRegex(PolicyDenied, "tool_proposal_write_authorization_required"):
                orchestrator.execute_tool_proposal(
                    context=OperationContext.create("proposal-write-denied"),
                    client=FakeMcpClient(),
                    tool_name="markers_add",
                    arguments={"name": "must-not-run"},
                )

    def test_state_compare_is_local_and_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ReadMcpClient()
            orchestrator = Orchestrator(DurableTaskStore(tmp))
            result = orchestrator.execute_tool_proposal(
                context=OperationContext.create("proposal-compare"),
                client=client,
                tool_name="state_compare",
                arguments={"before": {"x": 1}, "after": {"x": 2}},
            )

            self.assertEqual("completed", result["record"]["status"])
            self.assertFalse(result["result"]["state_compare"]["equal"])
            self.assertTrue(result["result"]["read_only"])
            self.assertEqual([], client.calls)

    def test_state_compare_requires_both_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PolicyDenied, "state_compare_inputs_required"):
                Orchestrator(DurableTaskStore(tmp)).execute_tool_proposal(
                    context=OperationContext.create("proposal-compare-missing"),
                    client=ReadMcpClient(),
                    tool_name="state_compare",
                    arguments={"before": {"x": 1}},
                )

    def test_state_compare_is_content_based(self):
        self.assertTrue(compare_state({"x": 1}, {"x": 1})["equal"])
        self.assertFalse(compare_state({"x": 1}, {"x": 2})["equal"])

    def test_router_keeps_local_privacy_boundary_and_blocks_when_unavailable(self):
        router = ModelRouter([
            ModelProvider("local", "ollama", {"planner"}, "local", True, priority=1, availability="online"),
            ModelProvider("cloud", "cloud", {"planner"}, "cloud", True, priority=2, availability="online"),
        ])
        self.assertEqual("local", router.select(role="planner", privacy_class="local").model_id)
        router.health("local", "unavailable")
        with self.assertRaises(ModelUnavailable):
            router.select(role="planner", privacy_class="local")

    def test_router_does_not_treat_unknown_health_as_available(self):
        router = ModelRouter([ModelProvider("unknown", "ollama", {"planner"}, "local")])
        with self.assertRaises(ModelUnavailable):
            router.select(role="planner", privacy_class="local")

    def test_model_retry_is_bounded_and_circuit_opens(self):
        router = ModelRouter([ModelProvider("local", "ollama", {"planner"}, "local", availability="online")])
        attempts = []

        def fail(_provider):
            attempts.append(True)
            raise RuntimeError("timeout")

        with self.assertRaises(ModelCallError):
            router.call_model("local", fail, retry=RetryPolicy(max_attempts=2), sleep=lambda _: None)
        self.assertEqual(2, len(attempts))
        router.record_failure("local")
        with self.assertRaises(ModelUnavailable):
            router.select(role="planner", privacy_class="local")

    def test_model_concurrency_limit_is_enforced(self):
        router = ModelRouter([
            ModelProvider(
                "local",
                "ollama",
                {"planner"},
                "local",
                max_concurrency=1,
                availability="online",
            )
        ])
        semaphore = router._semaphores["local"]
        self.assertTrue(semaphore.acquire())
        calls = []
        try:
            with self.assertRaisesRegex(ModelUnavailable, "provider_concurrency_limit"):
                router.call_model("local", lambda _provider: calls.append(True))
        finally:
            semaphore.release()
        self.assertEqual([], calls)

    def test_model_token_budget_blocks_before_second_call(self):
        router = ModelRouter([
            ModelProvider(
                "budgeted",
                "openrouter",
                {"planner"},
                "cloud",
                availability="online",
                token_budget_per_minute=10,
            )
        ])
        calls = []
        router.call_model("budgeted", lambda _provider: calls.append(True), requested_tokens=8)
        with self.assertRaisesRegex(ModelUnavailable, "provider_token_budget_exhausted"):
            router.call_model("budgeted", lambda _provider: calls.append(True), requested_tokens=3)
        self.assertEqual([True], calls)

    def test_orchestrator_requires_readback_and_restores_demo_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMcpClient()
            orchestrator = Orchestrator(DurableTaskStore(tmp))
            context = OperationContext.create("filmcraft-demo-1")
            result = orchestrator.run_mutation(
                context=context,
                client=client,
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )
            self.assertEqual("completed", result["record"]["status"])
            self.assertEqual(["original"], client.state["markers"])
            self.assertEqual("passed", result["record"]["validation_status"])
            self.assertTrue(result["result"]["success"])
            self.assertEqual(context.task_id, result["result"]["task_id"])
            self.assertEqual(context.run_id, result["result"]["run_id"])
            self.assertEqual(context.operation_id, result["result"]["operation_id"])
            self.assertTrue(result["result"]["undo_available"])
            self.assertEqual(result["record"]["before_state_hash"], result["result"]["before_state_hash"])
            self.assertEqual(result["record"]["after_state_hash"], result["result"]["after_state_hash"])
            events = [
                json.loads(line)
                for line in Path(tmp, "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            calls = [event for event in events if event["event_type"] == "mcp_call_finished"]
            self.assertEqual(
                ["state_snapshot", "markers_add", "state_snapshot", "edit_undo", "state_snapshot"],
                [event["tool_name"] for event in calls],
            )
            self.assertTrue(all("arguments_hash" in event for event in calls))
            self.assertNotIn("temporary", Path(tmp, "events.jsonl").read_text(encoding="utf-8"))

            repeat = orchestrator.run_mutation(
                context=context,
                client=client,
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )
            self.assertEqual(result["record"]["operation_id"], repeat["record"]["operation_id"])
            self.assertEqual(1, client.calls.count(("markers_add", {"name": "temporary"})))

    def test_false_mcp_success_is_blocked_and_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = OperationContext.create("filmcraft-false-success")
            result = Orchestrator(DurableTaskStore(tmp)).run_mutation(
                context=context,
                client=UnsuccessfulMcpClient(),
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )

            self.assertEqual("blocked", result["record"]["status"])
            self.assertEqual("mcp_result_not_success", result["error"])

    def test_filmcraft_adapter_maps_contract_tools_to_command_run(self):
        transport = FakeFilmCraftTransport()
        adapter = FilmCraftMcpAdapter(transport, project_id="demo", project_fingerprint="sha256:demo")
        adapter.markers_add(seconds=1.0, name="temporary")
        adapter.edit_undo()
        calls = [item for item in transport.requests if item[0] == "tools/call"]
        self.assertEqual("markers.add", calls[0][1]["arguments"]["id"])
        self.assertEqual("edit.undo", calls[1][1]["arguments"]["id"])

    def test_filmcraft_adapter_discovers_tools_before_calling(self):
        transport = FakeFilmCraftTransport()
        adapter = FilmCraftMcpAdapter(transport, project_id="demo", project_fingerprint="sha256:demo")
        adapter.project_inspect()
        self.assertEqual(["tools/list", "tools/call"], [item[0] for item in transport.requests])

    def test_filmcraft_adapter_fails_closed_for_missing_wire_tool(self):
        transport = MissingFilmCraftToolTransport()
        adapter = FilmCraftMcpAdapter(transport, project_id="demo", project_fingerprint="sha256:demo")
        with self.assertRaisesRegex(Exception, "tool_unavailable"):
            adapter.markers_add(seconds=1.0, name="temporary")
        self.assertEqual(["tools/list"], [item[0] for item in transport.requests])

    def test_filmcraft_adapter_rejects_malformed_or_duplicate_tool_schema(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                transport = MalformedFilmCraftSchemaTransport(duplicate=duplicate)
                adapter = FilmCraftMcpAdapter(
                    transport,
                    project_id="demo",
                    project_fingerprint="sha256:demo",
                )
                with self.assertRaisesRegex(Exception, "tools_list_invalid"):
                    adapter.project_inspect()

    def test_filmcraft_adapter_validates_arguments_before_wire_call(self):
        transport = RequiredArgumentFilmCraftTransport()
        adapter = FilmCraftMcpAdapter(transport, project_id="demo", project_fingerprint="sha256:demo")
        with self.assertRaisesRegex(Exception, "schema_invalid:project_inspect"):
            adapter.project_inspect()
        self.assertEqual(["tools/list"], [item[0] for item in transport.requests])

    def test_mutation_failure_is_durable_blocked_and_never_fake_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FailingMcpClient("mutation")
            context = OperationContext.create("filmcraft-mutation-timeout")
            result = Orchestrator(DurableTaskStore(tmp)).run_mutation(
                context=context,
                client=client,
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )

            self.assertEqual("blocked", result["record"]["status"])
            self.assertEqual("failed", result["record"]["validation_status"])
            self.assertEqual("mcp_timeout", result["error"])
            self.assertEqual("mcp_timeout", result["record"]["metadata"]["blocked_reason"])
            self.assertEqual("blocked", DurableTaskStore(tmp).get(context.task_id)["status"])

    def test_undo_failure_is_durable_blocked_after_mutation_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FailingMcpClient("undo")
            context = OperationContext.create("filmcraft-undo-timeout")
            result = Orchestrator(DurableTaskStore(tmp)).run_mutation(
                context=context,
                client=client,
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )

            self.assertEqual("blocked", result["record"]["status"])
            self.assertEqual("undo_timeout", result["error"])
            self.assertEqual("undo_timeout", result["record"]["metadata"]["blocked_reason"])

    def test_non_completed_idempotent_replay_does_not_call_mcp_or_fake_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FailingMcpClient("mutation")
            store = DurableTaskStore(tmp)
            orchestrator = Orchestrator(store)
            context = OperationContext.create("filmcraft-replay-blocked")
            first = orchestrator.run_mutation(
                context=context,
                client=client,
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )
            call_count = len(client.calls)

            second = orchestrator.run_mutation(
                context=context,
                client=client,
                tool_name="markers_add",
                arguments={"name": "temporary"},
                project_id="demo",
                project_fingerprint="sha256:demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )

            self.assertEqual("blocked", first["record"]["status"])
            self.assertIsNone(second["result"])
            self.assertEqual("idempotent_replay_not_completed", second["error"])
            self.assertEqual(call_count, len(client.calls))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from core.durable_task_store import DurableTaskStore, TaskStoreError
from core.filmcraft_adapter import FilmCraftMcpAdapter
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


class FakeFilmCraftTransport:
    def __init__(self):
        self.requests = []

    def request(self, method, params):
        self.requests.append((method, params))
        if method == "tools/call":
            name = params["name"]
            if name == "doc_inspect":
                text = json.dumps({"sequence": {"markers": []}})
            else:
                text = json.dumps({"success": True})
            return {"content": [{"type": "text", "text": text}]}
        return {"tools": []}


class OrchestratorV1Tests(unittest.TestCase):
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

    def test_policy_fails_closed_for_ambiguous_or_real_targets(self):
        policy = PolicyEngine()
        with self.assertRaises(PolicyDenied):
            policy.authorize(capability="disposable_write", project_id="current", project_fingerprint="x", disposable_project=True)
        with self.assertRaises(PolicyDenied):
            policy.authorize(capability="real_write", project_id="p", project_fingerprint="x")
        self.assertTrue(policy.authorize(capability="read").allowed)

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

    def test_filmcraft_adapter_maps_contract_tools_to_command_run(self):
        transport = FakeFilmCraftTransport()
        adapter = FilmCraftMcpAdapter(transport, project_id="demo", project_fingerprint="sha256:demo")
        adapter.markers_add(seconds=1.0, name="temporary")
        adapter.edit_undo()
        self.assertEqual("markers.add", transport.requests[0][1]["arguments"]["id"])
        self.assertEqual("edit.undo", transport.requests[1][1]["arguments"]["id"])


if __name__ == "__main__":
    unittest.main()

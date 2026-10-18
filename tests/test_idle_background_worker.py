import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from core.embedding_client import EmbeddingConfig, EmbeddingError
from core.autonomy import AutonomyLease
from core.idle_background_worker import (
    EmbeddingRefreshJob,
    IdleBackgroundWorker,
    IdleWorkerConfig,
)
from core.idle_readiness import build_readiness_report
from tools.run_idle_embedding_worker import (
    embedding_api_configured,
    external_embedding_allowed,
    frontmatter_status,
    next_sleep_seconds,
    should_stop_loop,
    write_heartbeat,
)


class FakeEmbeddingClient:
    config = EmbeddingConfig(model="nvidia/nemotron-3-embed-1b", dimension=4)

    def __init__(self, *, fail=None):
        self.calls = []
        self.fail = fail

    def embed(self, texts, *, input_type):
        self.calls.append((list(texts), input_type))
        if self.fail:
            raise EmbeddingError(self.fail)
        return [[float(index)] * 4 for index, _ in enumerate(texts, start=1)]


class IdleBackgroundWorkerTests(unittest.TestCase):
    def test_embedding_api_gate_requires_a_credential(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(embedding_api_configured())
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "nvapi-test"}, clear=True):
            self.assertTrue(embedding_api_configured())

    def test_external_embedding_requires_explicit_consent(self):
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "nvapi-test"}, clear=True):
            self.assertFalse(external_embedding_allowed())
        with patch.dict(
            "os.environ",
            {
                "NVIDIA_API_KEY": "nvapi-test",
                "WHITE_STUDIO_ALLOW_EXTERNAL_EMBEDDING": "1",
            },
            clear=True,
        ):
            self.assertTrue(external_embedding_allowed())

    def test_worker_fails_closed_without_external_embedding_consent(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        job = EmbeddingRefreshJob(vault, state, client=FakeEmbeddingClient())
        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="consent-gate-worker")

        result = worker.run_once(
            signals={
                "user_active": False,
                "cpu_percent": 1,
                "memory_percent": 1,
                "services_healthy": True,
                "external_embedding_allowed": False,
            },
            foreground_pending=False,
        )

        self.assertEqual("paused", result["status"])
        self.assertEqual("external_embedding_not_authorized", result["reason"])
        self.assertEqual([], list((state / "orchestrator" / "tasks").glob("*.json")))

    def test_loop_stops_on_terminal_failure_but_retries_pause(self):
        self.assertTrue(should_stop_loop("blocked", True))
        self.assertTrue(should_stop_loop("completed", True))
        self.assertFalse(should_stop_loop("paused", True))
        self.assertFalse(should_stop_loop("busy", True))
        self.assertFalse(should_stop_loop("deferred", True))
        self.assertTrue(should_stop_loop("paused", False))

    def test_deferred_backoff_reduces_polling(self):
        self.assertEqual(30, next_sleep_seconds({"status": "paused"}, 30))
        self.assertGreaterEqual(
            next_sleep_seconds(
                {"status": "deferred", "defer_until": "2999-01-01T00:00:00+00:00"},
                30,
            ),
            30,
        )

    def test_heartbeat_is_atomic_and_contains_no_credentials(self):
        path = Path(tempfile.mkdtemp(prefix="idle-heartbeat-")) / "heartbeat.json"
        payload = write_heartbeat(
            path,
            {"status": "paused", "reason": "foreground_task_pending", "task_id": "task-1"},
            loop=True,
        )
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("paused", payload["status"])
        self.assertEqual("task-1", saved["task_id"])
        self.assertNotIn("NVIDIA_API_KEY", path.read_text(encoding="utf-8"))

    def test_readiness_probe_does_not_infer_runtime_passes_from_config(self):
        state = Path(tempfile.mkdtemp(prefix="idle-readiness-"))
        report = build_readiness_report(state)
        self.assertEqual("ready", report["readiness"]["IDLE_ROUTER_READY"]["state"])
        self.assertEqual("ready", report["readiness"]["EMBEDDING_BACKGROUND_WORKER_READY"]["state"])
        self.assertEqual("pending_evidence", report["readiness"]["CHECKPOINT_RECOVERY_PASS"]["state"])
        self.assertEqual("pending_evidence", report["readiness"]["PREEMPTION_PASS"]["state"])
        self.assertFalse(report["overall"]["canonical_promotion_allowed"])

    def test_readiness_probe_recognizes_durable_proposal_and_pause(self):
        state = Path(tempfile.mkdtemp(prefix="idle-readiness-state-"))
        (state / "checkpoint.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "job_type": "embedding_refresh",
                    "task_id": "task-1",
                    "run_id": "run-1",
                    "operation_id": "op-1",
                    "idempotency_key": "idem-1",
                    "source_manifest_sha256": "sha-manifest",
                    "source_commit": "abc123",
                    "status": "paused",
                    "reason": "foreground_task_pending",
                }
            ),
            encoding="utf-8",
        )
        (state / "canonical-index-proposal.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "job_type": "embedding_refresh",
                    "status": "canonical-index-promotion-pending-approval",
                    "source_commit": "abc123",
                    "source_manifest_sha256": "sha-manifest",
                    "model_id": "nvidia/nemotron-3-embed-1b",
                    "vector_dimension": 2048,
                }
            ),
            encoding="utf-8",
        )
        report = build_readiness_report(state)
        self.assertEqual("observed", report["readiness"]["CHECKPOINT_RECOVERY_PASS"]["state"])
        self.assertEqual("observed", report["readiness"]["PREEMPTION_PASS"]["state"])
        self.assertEqual("ready", report["readiness"]["CANONICAL_INDEX_PROPOSAL_READY"]["state"])
        self.assertEqual(
            "pending_approval",
            report["readiness"]["CANONICAL_INDEX_PROMOTION_PENDING_APPROVAL"]["state"],
        )

    def test_readiness_keeps_preemption_evidence_after_recovery(self):
        state = Path(tempfile.mkdtemp(prefix="idle-readiness-recovered-"))
        (state / "checkpoint.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "job_type": "embedding_refresh",
                    "task_id": "task-1",
                    "run_id": "run-1",
                    "operation_id": "op-1",
                    "idempotency_key": "idem-1",
                    "source_manifest_sha256": "sha-manifest",
                    "source_commit": "abc123",
                    "status": "completed",
                    "preemption_observed": True,
                }
            ),
            encoding="utf-8",
        )
        report = build_readiness_report(state)
        self.assertEqual("observed", report["readiness"]["PREEMPTION_PASS"]["state"])

    def test_foreground_probe_reads_only_active_frontmatter(self):
        self.assertEqual("done", frontmatter_status("---\nstatus: done\n---\nstatus: queued\n"))
        self.assertEqual("queued", frontmatter_status("---\nstatus: queued\n---\n"))
        self.assertEqual("", frontmatter_status("# History\nstatus: queued\n"))

    def make_vault(self):
        root = Path(tempfile.mkdtemp(prefix="idle-vault-"))
        (root / "01-core").mkdir()
        (root / "91 外部知識").mkdir()
        (root / "ChatGPT 記憶資料庫").mkdir()
        (root / "runtime").mkdir()
        (root / "01-core" / "a.md").write_text("A", encoding="utf-8")
        (root / "91 外部知識" / "b.md").write_text("B", encoding="utf-8")
        (root / "ChatGPT 記憶資料庫" / "private.md").write_text("P", encoding="utf-8")
        (root / "runtime" / "ignored.md").write_text("R", encoding="utf-8")
        return root

    def test_idle_policy_and_foreground_preemption(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        client = FakeEmbeddingClient()
        job = EmbeddingRefreshJob(vault, state, client=client, config=IdleWorkerConfig(batch_size=2))
        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="test-worker")

        paused = worker.run_once(signals={"user_active": True, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True}, foreground_pending=False)
        self.assertEqual("paused", paused["status"])
        self.assertEqual("user_active", paused["reason"])
        paused = worker.run_once(signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True}, foreground_pending=True)
        self.assertEqual("foreground_task_pending", paused["reason"])

    def test_batch_checkpoint_resume_and_external_classification(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        client = FakeEmbeddingClient()
        job = EmbeddingRefreshJob(vault, state, client=client, config=IdleWorkerConfig(batch_size=1))
        first = job.run_batch()
        self.assertEqual("paused", first["status"])
        self.assertEqual(1, first["cursor"])
        second = job.run_batch()
        self.assertEqual("completed", second["status"])
        proposal = json.loads((state / "canonical-index-proposal.json").read_text(encoding="utf-8"))
        self.assertEqual("canonical-index-promotion-pending-approval", proposal["status"])
        self.assertEqual("PASS", json.loads((state / "validation.json").read_text(encoding="utf-8"))["status"])
        self.assertEqual("1.0.0", json.loads((state / "provenance.json").read_text(encoding="utf-8"))["schema_version"])
        records = [json.loads(line) for line in (state / "embedding-index.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual({"vault-markdown", "external-source"}, {item["source_class"] for item in records})
        self.assertNotIn("private.md", "".join(item["source_path"] for item in records))

        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="durable-worker")
        result = worker.run_once(
            signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
            foreground_pending=False,
        )
        self.assertIn("task_id", result)
        checkpoint = json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(result["task_id"], checkpoint["task_id"])
        self.assertTrue((state / "orchestrator" / "events.jsonl").exists())

    def test_dedupe_and_api_error_are_safe(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        client = FakeEmbeddingClient()
        job = EmbeddingRefreshJob(vault, state, client=client, config=IdleWorkerConfig(batch_size=8))
        self.assertEqual("completed", job.run_batch()["status"])
        before = (state / "embedding-index.jsonl").read_text(encoding="utf-8")
        job2 = EmbeddingRefreshJob(vault, state, client=client, config=IdleWorkerConfig(batch_size=8))
        self.assertEqual("completed", job2.run_batch()["status"])
        self.assertEqual(before, (state / "embedding-index.jsonl").read_text(encoding="utf-8"))

        failing = FakeEmbeddingClient(fail="embedding_request_failed")
        failed_job = EmbeddingRefreshJob(vault, state / "failed", client=failing)
        self.assertEqual("blocked", failed_job.run_batch()["status"])
        checkpoint = json.loads((state / "failed" / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual("embedding_request_failed", checkpoint["reason"])

    def test_transient_embedding_failure_is_bounded_deferred(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        failing = FakeEmbeddingClient(fail="embedding_rate_limited")
        job = EmbeddingRefreshJob(
            vault,
            state,
            client=failing,
            config=IdleWorkerConfig(
                batch_size=1,
                transient_defer_seconds=60,
                transient_defer_limit=2,
            ),
        )

        first = job.run_batch()
        self.assertEqual("deferred", first["status"])
        checkpoint = json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(1, checkpoint["defer_count"])
        self.assertEqual("embedding_rate_limited", checkpoint["reason"])
        self.assertGreater(checkpoint["defer_until"], checkpoint["updated_at"])

        # Active backoff prevents a second API call. This is not an unbounded
        # retry loop; the next pass waits for the checkpoint deadline.
        calls_after_first = len(failing.calls)
        self.assertEqual("deferred", job.run_batch()["status"])
        self.assertEqual(calls_after_first, len(failing.calls))

    def test_checkpoint_fails_closed_when_source_manifest_changes(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        client = FakeEmbeddingClient()
        job = EmbeddingRefreshJob(
            vault,
            state,
            client=client,
            config=IdleWorkerConfig(batch_size=1),
        )

        first = job.run_batch()
        self.assertEqual("paused", first["status"])
        self.assertEqual(1, first["cursor"])
        calls_before_drift = len(client.calls)

        (vault / "01-core" / "a.md").write_text("A changed", encoding="utf-8")
        second = job.run_batch()

        self.assertEqual("blocked", second["status"])
        self.assertEqual("source_manifest_changed", second["reason"])
        self.assertEqual(calls_before_drift, len(client.calls))
        checkpoint = json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual("blocked", checkpoint["status"])
        self.assertEqual("source_manifest_changed", checkpoint["reason"])

    def test_high_resource_signals_pause(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        job = EmbeddingRefreshJob(vault, state, client=FakeEmbeddingClient())
        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="test-worker")
        result = worker.run_once(signals={"user_active": False, "cpu_percent": 80, "memory_percent": 1, "external_embedding_allowed": True}, foreground_pending=False)
        self.assertEqual("high_cpu", result["reason"])

    def test_idle_worker_respects_foreground_autonomy_lease(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        shared_lease = state.parent / "autonomy" / "task.lease"
        foreground_lease = AutonomyLease(shared_lease)
        self.assertTrue(foreground_lease.acquire("foreground-runner"))
        try:
            job = EmbeddingRefreshJob(vault, state, client=FakeEmbeddingClient())
            worker = IdleBackgroundWorker(vault, state, job=job, worker_id="idle-worker")
            result = worker.run_once(
                signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
                foreground_pending=False,
            )
            self.assertEqual("busy", result["status"])
            self.assertEqual("idle_worker_lease_unavailable", result["reason"])
        finally:
            self.assertTrue(foreground_lease.release("foreground-runner"))

    def test_idle_worker_can_use_the_foreground_data_root_lease(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        shared_data = vault / "shared-data"
        foreground_lease = AutonomyLease(shared_data / "autonomy" / "task.lease")
        self.assertTrue(foreground_lease.acquire("foreground-runner"))
        try:
            job = EmbeddingRefreshJob(vault, state, client=FakeEmbeddingClient())
            worker = IdleBackgroundWorker(
                vault,
                state,
                job=job,
                autonomy_root=shared_data / "autonomy",
                worker_id="idle-worker",
            )
            result = worker.run_once(
                signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
                foreground_pending=False,
            )
            self.assertEqual("busy", result["status"])
            self.assertEqual("idle_worker_lease_unavailable", result["reason"])
        finally:
            self.assertTrue(foreground_lease.release("foreground-runner"))

    def test_foreground_probe_preempts_after_idle_check(self):
        vault = self.make_vault()
        (vault / "01-core" / "c.md").write_text("C", encoding="utf-8")
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        client = FakeEmbeddingClient()
        job = EmbeddingRefreshJob(vault, state, client=client, config=IdleWorkerConfig(batch_size=2))
        foreground = {"pending": False}
        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="preempt-worker")

        def probe():
            return foreground["pending"]

        original = client.embed

        def embed_and_activate(texts, *, input_type):
            result = original(texts, input_type=input_type)
            foreground["pending"] = True
            return result

        client.embed = embed_and_activate
        result = worker.run_once(
            signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
            foreground_pending=False,
            foreground_probe=probe,
        )
        self.assertEqual("paused", result["status"])
        self.assertEqual("foreground_task_or_user_activity", json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))["reason"])
        durable = json.loads((state / "orchestrator" / "tasks" / f"{result['task_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual("paused", durable["status"])
        self.assertEqual("pending", durable["validation_status"])
        self.assertEqual("paused", durable["metadata"]["checkpoint_status"])

    def test_foreground_probe_after_task_creation_persists_paused_state(self):
        vault = self.make_vault()
        (vault / "01-core" / "c.md").write_text("C", encoding="utf-8")
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        job = EmbeddingRefreshJob(vault, state, client=FakeEmbeddingClient())
        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="late-preempt-worker")
        probe_calls = {"count": 0}

        def probe():
            probe_calls["count"] += 1
            return probe_calls["count"] == 1

        result = worker.run_once(
            signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1, "external_embedding_allowed": True},
            foreground_pending=False,
            foreground_probe=probe,
        )

        self.assertEqual("paused", result["status"])
        checkpoint = json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual("paused", checkpoint["status"])
        self.assertEqual("foreground_task_pending", checkpoint["reason"])
        self.assertTrue(checkpoint["preemption_observed"])
        durable = json.loads((state / "orchestrator" / "tasks" / f"{result['task_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual("paused", durable["status"])
        self.assertEqual("pending", durable["validation_status"])
        self.assertEqual("foreground_task_pending", durable["metadata"]["pause_reason"])


if __name__ == "__main__":
    unittest.main()

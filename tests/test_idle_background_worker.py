import json
import tempfile
import unittest
from pathlib import Path

from core.embedding_client import EmbeddingConfig, EmbeddingError
from core.idle_background_worker import (
    EmbeddingRefreshJob,
    IdleBackgroundWorker,
    IdleWorkerConfig,
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

        paused = worker.run_once(signals={"user_active": True, "cpu_percent": 1, "memory_percent": 1}, foreground_pending=False)
        self.assertEqual("paused", paused["status"])
        self.assertEqual("user_active", paused["reason"])
        paused = worker.run_once(signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1}, foreground_pending=True)
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
            signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1},
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

    def test_high_resource_signals_pause(self):
        vault = self.make_vault()
        state = vault / "runtime" / ".mcp-state" / "embedding-index"
        job = EmbeddingRefreshJob(vault, state, client=FakeEmbeddingClient())
        worker = IdleBackgroundWorker(vault, state, job=job, worker_id="test-worker")
        result = worker.run_once(signals={"user_active": False, "cpu_percent": 80, "memory_percent": 1}, foreground_pending=False)
        self.assertEqual("high_cpu", result["reason"])

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
            signals={"user_active": False, "cpu_percent": 1, "memory_percent": 1},
            foreground_pending=False,
            foreground_probe=probe,
        )
        self.assertEqual("paused", result["status"])
        self.assertEqual("foreground_task_or_user_activity", json.loads((state / "checkpoint.json").read_text(encoding="utf-8"))["reason"])


if __name__ == "__main__":
    unittest.main()

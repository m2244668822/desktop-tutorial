import tempfile
import unittest
from pathlib import Path

from core.autonomy import AutonomyQueue


class FailedTaskAutoRetryContractTests(unittest.TestCase):
    def test_failed_task_is_terminal_and_not_reclaimed_implicitly(self):
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / "autonomy" / "task_queue.json")
            task = queue.enqueue("補測試", category="test")
            runner = AutonomyRunner(
                data_root,
                executor=lambda claimed: (_ for _ in ()).throw(RuntimeError("failed")),
            )

            first = runner.evaluate_once(
                {"user_active": False, "quota_sufficient": True, "services_healthy": True}
            )
            second = runner.evaluate_once(
                {"user_active": False, "quota_sufficient": True, "services_healthy": True}
            )
            stored = {item["id"]: item for item in queue.tasks()}[task["id"]]

        self.assertEqual("failed", first["status"])
        self.assertEqual("failed", stored["status"])
        self.assertEqual("idle", second["status"])

    def test_parallel_running_task_blocks_second_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = AutonomyQueue(Path(tmp) / "queue.json")
            queue.enqueue("第一項", category="test", priority=1)
            queue.enqueue("第二項", category="test", priority=2)

            first = queue.claim_next("worker-a")
            second = queue.claim_next("worker-b")

        self.assertIsNotNone(first)
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()

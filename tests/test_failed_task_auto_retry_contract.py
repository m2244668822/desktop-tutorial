import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PY = ROOT / ".sync_user_project" / "chatgpt_server.py"


class FailedTaskAutoRetryContractTests(unittest.TestCase):
    def setUp(self):
        self.src = SERVER_PY.read_text(encoding="utf-8")

    def test_auto_retry_settings_and_runtime_keys_exist(self):
        self.assertIn("AGENT_TASK_AUTO_RETRY_ENABLED", self.src)
        self.assertIn("AGENT_TASK_AUTO_RETRY_MIN_INTERVAL_SECONDS", self.src)
        self.assertIn("AGENT_TASK_AUTO_RETRY_LIMIT", self.src)
        self.assertIn('"last_failed_retry_status": "idle"', self.src)

    def test_requeue_checks_active_retry_chain(self):
        self.assertIn("def _has_active_retry_task(", self.src)
        self.assertIn('"reason": "active_retry_exists"', self.src)
        self.assertIn("retry_from_task_id=", self.src)

    def test_cns_cycle_runs_failed_task_recovery(self):
        self.assertIn("def run_failed_task_auto_retry_cycle(", self.src)
        self.assertIn("failed_task_recovery = run_failed_task_auto_retry_cycle(", self.src)
        self.assertIn('"failed_task_recovery": failed_task_recovery', self.src)


if __name__ == "__main__":
    unittest.main()

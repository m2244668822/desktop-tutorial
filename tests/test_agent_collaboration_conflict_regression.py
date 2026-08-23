import unittest
from pathlib import Path

from desktop_chat_app import DesktopBridge


ROOT = Path(__file__).resolve().parents[1]
CHAT_SHELL = (ROOT / "templates" / "chat_shell.html").read_text(encoding="utf-8")
MONITOR_SHELL = (ROOT / "templates" / "monitor_shell.html").read_text(encoding="utf-8")


class AgentCollaborationConflictRegressionTests(unittest.TestCase):
    def test_git_status_snapshot_is_not_mock_limited(self):
        bridge = DesktopBridge(energy_lite=True)
        try:
            status = bridge._git_status_filtered(short=True)
        finally:
            bridge.stop_background_monitor()

        self.assertTrue(status.strip())
        self.assertNotIn("Git 功能受限 (Mock)", status)

    def test_frontend_abort_timeout_is_long_enough_for_agent_workflows(self):
        for html in (CHAT_SHELL, MONITOR_SHELL):
            self.assertNotIn("ctrl.abort(), 45000", html)
            self.assertIn("AGENT_REQUEST_TIMEOUT_MS", html)
            self.assertIn("signal is aborted without reason", html)
            self.assertIn("E_CLIENT_ABORT", html)
            self.assertIn("智能體任務仍在處理", html)


if __name__ == "__main__":
    unittest.main()

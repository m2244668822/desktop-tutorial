import unittest
from pathlib import Path

from core import openclaw_bridge


class OpenClawBridgeTests(unittest.TestCase):
    def test_stopped_daemon_surfaces_governance_gate(self):
        old_run = openclaw_bridge._run_command
        try:
            def fake_run(cmd, timeout=8):
                if cmd[:3] == ["cmd", "/c", "openclaw --version"]:
                    return 0, "OpenClaw 2026.5.27 (abc123)", ""
                if cmd[:2] == ["schtasks", "/Query"]:
                    return 0, "TaskName: OpenClaw Gateway\nStatus:                               Ready", ""
                return 1, "", "unexpected"

            openclaw_bridge._run_command = fake_run

            status = openclaw_bridge.detect_openclaw_status(Path("E:/智能體"))

            self.assertTrue(status["installed"])
            self.assertTrue(status["daemon_installed"])
            self.assertFalse(status["daemon_running"])
            self.assertEqual(status["daemon_state"], "stopped")
            self.assertEqual(status["health"], "governed_stopped")
            self.assertEqual(
                status["governance"]["decision_state"],
                "prophet_decision_required",
            )
            self.assertFalse(status["governance"]["auto_start_allowed"])
            self.assertTrue(status["governance"]["prophet_required_for_mutation"])
        finally:
            openclaw_bridge._run_command = old_run

    def test_missing_cli_reports_unavailable_governance(self):
        old_run = openclaw_bridge._run_command
        try:
            openclaw_bridge._run_command = lambda *args, **kwargs: (
                1,
                "",
                "not found",
            )

            status = openclaw_bridge.detect_openclaw_status()

            self.assertFalse(status["installed"])
            self.assertEqual(status["health"], "unavailable")
            self.assertEqual(status["governance"]["decision_state"], "cli_unavailable")
        finally:
            openclaw_bridge._run_command = old_run


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

from core import openclaw_bridge


class OpenClawBridgeTests(unittest.TestCase):
    def test_stopped_daemon_surfaces_governance_gate(self):
        old_run = openclaw_bridge._run_command
        old_gateway = openclaw_bridge.detect_gateway_health
        try:
            def fake_run(cmd, timeout=8):
                if cmd[:3] == ["cmd", "/c", "openclaw --version"]:
                    return 0, "OpenClaw 2026.5.27 (abc123)", ""
                if cmd[:2] == ["schtasks", "/Query"]:
                    return 0, "TaskName: OpenClaw Gateway\nStatus:                               Ready", ""
                return 1, "", "unexpected"

            openclaw_bridge._run_command = fake_run
            openclaw_bridge.detect_gateway_health = lambda: {
                "host": "127.0.0.1",
                "port": 18789,
                "url": "http://127.0.0.1:18789/healthz",
                "listening": False,
                "health_ok": False,
                "response": {"ok": False, "error": "port_not_listening"},
            }

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
            self.assertFalse(status["local_execution"]["supported"])
        finally:
            openclaw_bridge._run_command = old_run
            openclaw_bridge.detect_gateway_health = old_gateway

    def test_live_gateway_proves_local_execution_even_when_task_status_ready(self):
        old_run = openclaw_bridge._run_command
        old_gateway = openclaw_bridge.detect_gateway_health
        try:
            def fake_run(cmd, timeout=8):
                if cmd[:3] == ["cmd", "/c", "openclaw --version"]:
                    return 0, "OpenClaw 2026.5.27 (abc123)", ""
                if cmd[:2] == ["schtasks", "/Query"]:
                    return 0, "TaskName: OpenClaw Gateway\nStatus:                               Ready", ""
                return 1, "", "unexpected"

            openclaw_bridge._run_command = fake_run
            openclaw_bridge.detect_gateway_health = lambda: {
                "host": "127.0.0.1",
                "port": 18789,
                "url": "http://127.0.0.1:18789/healthz",
                "listening": True,
                "health_ok": True,
                "response": {"ok": True, "status_code": 200, "data": {"ok": True, "status": "live"}},
            }

            status = openclaw_bridge.detect_openclaw_status(Path("E:/智能體"))

            self.assertTrue(status["installed"])
            self.assertTrue(status["daemon_installed"])
            self.assertTrue(status["daemon_running"])
            self.assertEqual(status["daemon_state"], "running")
            self.assertEqual(status["health"], "ready")
            self.assertTrue(status["local_execution"]["supported"])
            self.assertEqual(status["governance"]["decision_state"], "running")
            self.assertIn("task_not_running_but_gateway_live", status["notes"])
        finally:
            openclaw_bridge._run_command = old_run
            openclaw_bridge.detect_gateway_health = old_gateway

    def test_missing_cli_reports_unavailable_governance(self):
        old_run = openclaw_bridge._run_command
        old_gateway = openclaw_bridge.detect_gateway_health
        try:
            openclaw_bridge._run_command = lambda *args, **kwargs: (
                1,
                "",
                "not found",
            )
            openclaw_bridge.detect_gateway_health = lambda: {
                "host": "127.0.0.1",
                "port": 18789,
                "url": "http://127.0.0.1:18789/healthz",
                "listening": False,
                "health_ok": False,
                "response": {"ok": False, "error": "port_not_listening"},
            }

            status = openclaw_bridge.detect_openclaw_status()

            self.assertFalse(status["installed"])
            self.assertEqual(status["health"], "unavailable")
            self.assertEqual(status["governance"]["decision_state"], "cli_unavailable")
        finally:
            openclaw_bridge._run_command = old_run
            openclaw_bridge.detect_gateway_health = old_gateway

    def test_non_windows_uses_direct_cli_and_skips_windows_task_query(self):
        old_run = openclaw_bridge._run_command
        old_gateway = openclaw_bridge.detect_gateway_health
        calls = []
        try:
            def fake_run(cmd, timeout=8):
                calls.append(cmd)
                if cmd == ["openclaw", "--version"]:
                    return 0, "OpenClaw 2026.5.27 (abc123)", ""
                return 1, "", "unexpected command"

            openclaw_bridge._run_command = fake_run
            openclaw_bridge.detect_gateway_health = lambda: {
                "host": "127.0.0.1",
                "port": 18789,
                "url": "http://127.0.0.1:18789/healthz",
                "listening": True,
                "health_ok": True,
                "response": {"ok": True, "status_code": 200, "data": {"ok": True, "status": "live"}},
            }

            status = openclaw_bridge.detect_openclaw_status(
                Path("/repo"),
                system_name="Darwin",
            )

            self.assertTrue(status["installed"])
            self.assertTrue(status["local_execution"]["supported"])
            self.assertTrue(status["daemon_running"])
            self.assertEqual(status["daemon_state"], "running")
            self.assertEqual(status["health"], "ready")
            self.assertIn("windows_scheduled_task_not_applicable", status["notes"])
            self.assertNotIn(
                ["schtasks", "/Query", "/TN", "OpenClaw Gateway", "/FO", "LIST", "/V"],
                calls,
            )
        finally:
            openclaw_bridge._run_command = old_run
            openclaw_bridge.detect_gateway_health = old_gateway


if __name__ == "__main__":
    unittest.main()

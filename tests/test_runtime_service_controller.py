import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_service_controller.py"
SPEC = importlib.util.spec_from_file_location("runtime_service_controller", MODULE_PATH)
runtime_service_controller = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["runtime_service_controller"] = runtime_service_controller
SPEC.loader.exec_module(runtime_service_controller)


class RuntimeServiceControllerTests(unittest.TestCase):
    def test_status_reports_missing_ports_without_launching(self):
        spec = runtime_service_controller.ServiceSpec(
            "web",
            (5001,),
            ("python", "system_main.py"),
            {},
            "logs/web.log",
        )
        launched = []

        result = runtime_service_controller.control_service(
            spec,
            action="status",
            port_checker=lambda _port: False,
            launcher=lambda service, root: launched.append(service.name) or (123, ""),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "not_listening")
        self.assertEqual(result.action, "status_only")
        self.assertEqual(launched, [])

    def test_dry_run_does_not_launch_missing_service(self):
        spec = runtime_service_controller.ServiceSpec(
            "n8n",
            (5678, 5679),
            ("n8n", "start"),
            {},
            "logs/n8n.log",
        )
        launched = []

        result = runtime_service_controller.control_service(
            spec,
            action="start",
            dry_run=True,
            port_checker=lambda _port: False,
            launcher=lambda service, root: launched.append(service.name) or (123, ""),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "would_start")
        self.assertEqual(result.action, "dry_run")
        self.assertEqual(launched, [])

    def test_openclaw_requires_explicit_governance_flag(self):
        spec = runtime_service_controller.ServiceSpec(
            "openclaw",
            (18789,),
            ("openclaw", "gateway", "--port", "18789"),
            {},
            "logs/openclaw.log",
            governed=True,
        )

        result = runtime_service_controller.control_service(
            spec,
            action="start",
            port_checker=lambda _port: False,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "governance_required")
        self.assertEqual(result.action, "governed_skip")
        self.assertIn("--allow-openclaw-mutation", result.error)

    def test_start_waits_until_all_ports_are_listening(self):
        spec = runtime_service_controller.ServiceSpec(
            "n8n",
            (5678, 5679),
            ("n8n", "start"),
            {},
            "logs/n8n.log",
        )
        calls = []

        def fake_port(port):
            calls.append(port)
            return len(calls) > 2

        result = runtime_service_controller.control_service(
            spec,
            action="start",
            wait_seconds=2,
            port_checker=fake_port,
            launcher=lambda _service, _root: (456, ""),
            sleep=lambda _seconds: None,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.pid, 456)
        self.assertEqual(result.action, "start")

    def test_parse_components_rejects_unknown_names(self):
        specs = {"web": object()}

        with self.assertRaises(ValueError):
            runtime_service_controller.parse_components("web,unknown", specs)

    def test_platform_specs_use_expected_openclaw_commands(self):
        win = runtime_service_controller.service_specs(Path("C:/repo"), "Windows")
        mac = runtime_service_controller.service_specs(Path("/repo"), "Darwin")

        self.assertTrue(win["openclaw"].governed)
        self.assertTrue(mac["openclaw"].governed)
        self.assertIn("gateway.cmd", win["openclaw"].command[0])
        self.assertEqual(mac["web"].command[0], "bash")
        self.assertEqual(mac["openclaw"].command[:3], ("openclaw", "gateway", "--port"))

    def test_payload_contains_next_actions_for_unready_services(self):
        result = runtime_service_controller.ServiceResult(
            name="openclaw",
            ports={"18789": False},
            ok=False,
            status="governance_required",
            action="governed_skip",
            command=["openclaw", "gateway", "--port", "18789"],
            log_file="logs/openclaw.log",
            pid=None,
            error="approval required",
            governed=True,
        )

        payload = runtime_service_controller.build_payload([result], Path("/repo"))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "attention_required")
        self.assertEqual(payload["next_actions"][0]["source"], "openclaw")
        self.assertTrue(payload["next_actions"][0]["governed"])
        self.assertIn("Approve", payload["next_actions"][0]["summary"])
        self.assertIn("--allow-openclaw-mutation", payload["next_actions"][0]["controller_command"])


if __name__ == "__main__":
    unittest.main()

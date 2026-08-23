import importlib.util
import plistlib
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrevorAutonomyLaunchAgentTests(unittest.TestCase):
    def test_launchagent_contract_is_persistent_and_secret_free(self):
        module_name = "tools.install_trevor_autonomy_launchagent"
        self.assertIsNotNone(importlib.util.find_spec(module_name))
        from tools.install_trevor_autonomy_launchagent import render_launchagent

        rendered = render_launchagent(
            root=ROOT,
            python_executable=Path("/opt/trevor/python"),
            data_root=Path("/var/lib/trevor-test"),
            log_root=Path("/var/log/trevor-test"),
        )
        payload = plistlib.loads(rendered.encode("utf-8"))

        self.assertEqual("com.trevor.autonomy", payload["Label"])
        self.assertTrue(payload["RunAtLoad"])
        self.assertIs(payload["KeepAlive"], True)
        self.assertEqual("Background", payload["ProcessType"])
        self.assertEqual("/opt/trevor/python", payload["ProgramArguments"][0])
        self.assertIn(
            str(ROOT / "tools" / "agent_autonomy_daemon.py"),
            payload["ProgramArguments"],
        )
        self.assertIn("60", payload["ProgramArguments"])
        self.assertIn("900", payload["ProgramArguments"])
        self.assertEqual(
            "/var/lib/trevor-test",
            payload["EnvironmentVariables"]["TREVOR_DATA_DIR"],
        )
        environment_text = str(payload["EnvironmentVariables"])
        self.assertNotIn("API_KEY", environment_text)
        self.assertNotIn("TOKEN", environment_text)

    def test_reload_waits_for_bootout_and_retries_transient_bootstrap(self):
        from tools.install_trevor_autonomy_launchagent import reload_launchagent

        print_results = iter([0, 113])
        bootstrap_results = iter([5, 0])
        commands = []

        def runner(command, **kwargs):
            commands.append(command)
            action = command[1]
            if action == "print":
                return subprocess.CompletedProcess(command, next(print_results))
            if action == "bootstrap":
                return subprocess.CompletedProcess(command, next(bootstrap_results))
            return subprocess.CompletedProcess(command, 0)

        reload_launchagent(
            Path("/tmp/com.trevor.autonomy.plist"),
            uid=501,
            runner=runner,
            sleeper=lambda delay: None,
        )

        bootstrap_commands = [command for command in commands if command[1] == "bootstrap"]
        self.assertEqual(2, len(bootstrap_commands))


if __name__ == "__main__":
    unittest.main()

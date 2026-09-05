import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "tools" / "manage_trevor_autonomy_windows.ps1"


class WindowsAutonomyManagerContractTests(unittest.TestCase):
    def test_manager_has_reversible_lifecycle_and_hidden_launch(self):
        content = MANAGER.read_text(encoding="utf-8")

        for action in ("start", "stop", "restart", "status", "install", "uninstall"):
            self.assertIn(f'"{action}"', content)
        self.assertIn("Register-ScheduledTask", content)
        self.assertIn("Unregister-ScheduledTask", content)
        self.assertIn("HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", content)
        self.assertIn("Remove-ItemProperty", content)
        self.assertIn("-WindowStyle Hidden", content)
        self.assertIn('"--unset-env", "TREVOR_MEMORY_KEY_B64"', content)
        self.assertIn("agent_autonomy_daemon.py", content)

    def test_detached_launcher_supports_secret_environment_removal(self):
        from tools.launch_detached import parse_args

        args = parse_args(
            [
                "--cwd", ".",
                "--pidfile", "worker.pid",
                "--stdout", "worker.out",
                "--stderr", "worker.err",
                "--unset-env", "TREVOR_MEMORY_KEY_B64",
                "--", "python", "worker.py",
            ]
        )

        self.assertEqual(["TREVOR_MEMORY_KEY_B64"], args.unset_env)
        self.assertEqual(["python", "worker.py"], args.command)


if __name__ == "__main__":
    unittest.main()

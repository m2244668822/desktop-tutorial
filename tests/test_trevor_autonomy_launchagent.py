import importlib.util
import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_MANAGER = ROOT / "tools" / "manage_trevor_autonomy.sh"


class TrevorAutonomyLaunchAgentTests(unittest.TestCase):
    def test_external_volume_fallback_manager_is_noninteractive_and_bounded(self):
        self.assertTrue(AUTONOMY_MANAGER.exists())
        content = AUTONOMY_MANAGER.read_text(encoding="utf-8")
        self.assertIn("launch_detached.py", content)
        self.assertIn("TREVOR_DISABLE_KEYCHAIN=true", content)
        self.assertIn("--heartbeat 60", content)
        self.assertIn("--evaluation 900", content)
        self.assertIn(".venv312", content)

    def test_python_path_preserves_virtualenv_symlink(self):
        from tools.install_trevor_autonomy_launchagent import normalize_executable_path

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            interpreter = root / "python3.12"
            interpreter.write_text("", encoding="utf-8")
            virtualenv_python = root / "venv-python"
            virtualenv_python.symlink_to(interpreter)

            self.assertEqual(
                virtualenv_python,
                normalize_executable_path(str(virtualenv_python)),
            )

    def test_launchagent_contract_is_persistent_and_secret_free(self):
        module_name = "tools.install_trevor_autonomy_launchagent"
        self.assertIsNotNone(importlib.util.find_spec(module_name))
        from tools.install_trevor_autonomy_launchagent import render_launchagent

        rendered = render_launchagent(
            root=ROOT,
            python_executable=Path("/opt/trevor/python"),
            data_root=Path("/var/lib/trevor-test"),
            log_root=Path("/var/log/trevor-test"),
            credential_root=Path("/var/lib/trevor-credentials"),
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
        self.assertEqual(
            "true",
            payload["EnvironmentVariables"]["TREVOR_DISABLE_KEYCHAIN"],
        )
        self.assertEqual(
            "/var/lib/trevor-credentials",
            payload["EnvironmentVariables"]["CREDENTIALS_DIRECTORY"],
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

    def test_private_credentials_are_required_before_disabling_keychain(self):
        from tools.install_trevor_autonomy_launchagent import (
            validate_private_credential_root,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            root.chmod(0o700)
            for name in ('nvidia_api_key', 'trevor_memory_key_b64'):
                path = root / name
                path.write_text('configured', encoding='utf-8')
                path.chmod(0o400)

            self.assertEqual(root.resolve(), validate_private_credential_root(root))

            os.chmod(root / 'nvidia_api_key', 0o644)
            with self.assertRaisesRegex(RuntimeError, 'credential_file_permissions'):
                validate_private_credential_root(root)

    def test_custom_data_root_requires_backend_alignment(self):
        from tools.install_trevor_autonomy_launchagent import ensure_data_root_alignment

        ensure_data_root_alignment(Path('/canonical'), Path('/canonical'))
        with self.assertRaisesRegex(RuntimeError, 'custom_data_dir_requires_backend_alignment'):
            ensure_data_root_alignment(Path('/custom'), Path('/canonical'))

    def test_external_volume_install_uses_terminal_safe_manager(self):
        source = (
            ROOT / 'tools' / 'install_trevor_autonomy_launchagent.py'
        ).read_text(encoding='utf-8')

        self.assertIn('is_external_volume(ROOT)', source)
        self.assertIn('manage_trevor_autonomy.sh', source)

    def test_documented_health_check_requires_autonomy_readiness(self):
        documentation = (ROOT / 'deploy' / 'README.md').read_text(encoding='utf-8')

        self.assertIn("payload['autonomy']['ready']", documentation)


if __name__ == "__main__":
    unittest.main()

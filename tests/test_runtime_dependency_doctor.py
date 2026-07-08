import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_dependency_doctor.py"
SPEC = importlib.util.spec_from_file_location("runtime_dependency_doctor", MODULE_PATH)
runtime_dependency_doctor = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["runtime_dependency_doctor"] = runtime_dependency_doctor
SPEC.loader.exec_module(runtime_dependency_doctor)


def ok_runner(cmd, timeout=8):
    return {"returncode": 0, "stdout": "version ok", "stderr": "", "error": ""}


class RuntimeDependencyDoctorTests(unittest.TestCase):
    def test_invalid_ffmpeg_env_blocks_even_when_path_has_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-ffmpeg.exe"
            env = {"FFMPEG_PATH": str(missing), "PATH": ""}

            probe = runtime_dependency_doctor.probe_ffmpeg(
                env=env,
                runner=ok_runner,
                which=lambda _name: "C:/tools/ffmpeg.exe",
            )

            self.assertFalse(probe.ok)
            self.assertEqual(probe.status, "configured_path_not_found")
            self.assertEqual(probe.detail["resolution"]["source"], "FFMPEG_PATH")
            self.assertEqual(probe.detail["resolution"]["path_lookup"], "C:/tools/ffmpeg.exe")

    def test_ffmpeg_env_command_name_can_resolve_through_path(self):
        env = {"FFMPEG_PATH": "ffmpeg", "PATH": "x"}

        probe = runtime_dependency_doctor.probe_ffmpeg(
            env=env,
            runner=ok_runner,
            which=lambda name: "/opt/homebrew/bin/ffmpeg" if name == "ffmpeg" else None,
        )

        self.assertTrue(probe.ok)
        self.assertEqual(probe.status, "ready")
        self.assertEqual(probe.detail["resolution"]["source"], "FFMPEG_PATH")

    def test_shell_context_reports_stale_workspace_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {"CODEX_WORKSPACE": str(root / "old-clone"), "PATH": ""}

            probe = runtime_dependency_doctor.probe_shell_context(root, env=env, system_name="Darwin")

            self.assertFalse(probe.ok)
            self.assertEqual(probe.status, "stale_env_paths")
            self.assertFalse(probe.detail["env_paths"]["CODEX_WORKSPACE"]["exists"])

    def test_project_python_uses_platform_specific_venv_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv_python = root / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("# stub", encoding="utf-8")

            probe = runtime_dependency_doctor.probe_project_python(
                root,
                system_name="Darwin",
                runner=ok_runner,
            )

            self.assertTrue(probe.ok)
            self.assertEqual(probe.status, "ready")
            self.assertEqual(probe.detail["venv_python"], str(venv_python))

    def test_payload_promotes_failed_probes_to_next_actions(self):
        probe = runtime_dependency_doctor.Probe(
            "ffmpeg",
            False,
            "missing",
            {"resolution": {"source": "missing"}},
            {
                "summary": "Install FFmpeg",
                "windows": ["winget install Gyan.FFmpeg"],
                "macos": ["brew install ffmpeg"],
                "verify": "ffmpeg -version",
            },
        )

        payload = runtime_dependency_doctor.build_payload([probe], Path("repo"))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["failed_count"], 1)
        self.assertEqual(payload["next_actions"][0]["source"], "ffmpeg")
        self.assertIn("Install FFmpeg", payload["next_actions"][0]["summary"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_binary_locator.py"
SPEC = importlib.util.spec_from_file_location("runtime_binary_locator", MODULE_PATH)
runtime_binary_locator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["runtime_binary_locator"] = runtime_binary_locator
SPEC.loader.exec_module(runtime_binary_locator)


class RuntimeBinaryLocatorTests(unittest.TestCase):
    def test_ffmpeg_resolves_winget_candidate_when_path_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = (
                root
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
                / "ffmpeg-8.1.2-full_build"
                / "bin"
            )
            package.mkdir(parents=True)
            ffmpeg = package / "ffmpeg.exe"
            ffmpeg.write_text("stub", encoding="utf-8")

            result = runtime_binary_locator.resolve_ffmpeg(
                env={"LOCALAPPDATA": str(root), "PATH": ""},
                which=lambda _name: None,
            )

            self.assertTrue(result["found"])
            self.assertEqual(result["source"], "candidate")
            self.assertEqual(result["path"], str(ffmpeg))

    def test_invalid_explicit_env_still_blocks_candidate_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = (
                root
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
                / "ffmpeg-8.1.2-full_build"
                / "bin"
            )
            package.mkdir(parents=True)
            (package / "ffmpeg.exe").write_text("stub", encoding="utf-8")
            missing = root / "missing.exe"

            result = runtime_binary_locator.resolve_ffmpeg(
                env={"LOCALAPPDATA": str(root), "FFMPEG_PATH": str(missing), "PATH": ""},
                which=lambda _name: None,
            )

            self.assertFalse(result["found"])
            self.assertEqual(result["source"], "FFMPEG_PATH")
            self.assertEqual(result["error"], "configured_path_not_found")


if __name__ == "__main__":
    unittest.main()

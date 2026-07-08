import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "repo_secret_hygiene.py"
SPEC = importlib.util.spec_from_file_location("repo_secret_hygiene", MODULE_PATH)
repo_secret_hygiene = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["repo_secret_hygiene"] = repo_secret_hygiene
SPEC.loader.exec_module(repo_secret_hygiene)


def run_git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


class RepoSecretHygieneTests(unittest.TestCase):
    def test_build_payload_passes_clean_tracked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_git(root, "init")
            run_git(root, "config", "user.email", "test@example.com")
            run_git(root, "config", "user.name", "Test")
            (root / ".gitignore").write_text(
                "\n".join(
                    [
                        ".env",
                        ".env.*.local",
                        "*.key",
                        "*.pem",
                        "data/",
                        "logs/",
                        "reports/*.json",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text("print('clean')\n", encoding="utf-8")
            run_git(root, "add", ".")

            payload = repo_secret_hygiene.build_payload(root)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["finding_count"], 0)
            self.assertTrue(payload["gitignore"]["ok"])

    def test_build_payload_detects_tracked_secret_without_revealing_full_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_git(root, "init")
            secret_value = "sk-" + ("A" * 32)
            (root / ".gitignore").write_text(
                ".env\n.env.*.local\n*.key\n*.pem\ndata/\nlogs/\nreports/*.json\n",
                encoding="utf-8",
            )
            (root / "config.py").write_text(f"API_KEY = '{secret_value}'\n", encoding="utf-8")
            run_git(root, "add", ".")

            payload = repo_secret_hygiene.build_payload(root)

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["finding_count"], 1)
            finding = payload["findings"][0]
            self.assertEqual(finding["pattern"], "openai_api_key")
            self.assertNotIn(secret_value, finding["redacted"])
            self.assertTrue(finding["redacted"].startswith("sk-A"))

    def test_missing_gitignore_patterns_create_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_git(root, "init")
            (root / ".gitignore").write_text(".env\n", encoding="utf-8")
            (root / "app.py").write_text("print('clean')\n", encoding="utf-8")
            run_git(root, "add", ".")

            payload = repo_secret_hygiene.build_payload(root)

            self.assertFalse(payload["ok"])
            self.assertIn("*.pem", payload["gitignore"]["missing"])
            self.assertEqual(payload["next_actions"][0]["status"], "missing_gitignore_patterns")


if __name__ == "__main__":
    unittest.main()

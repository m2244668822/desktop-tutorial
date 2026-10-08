import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INBOX_E2E = ROOT / "services" / "inbox_executor" / "src" / "e2e.js"
NODE_FILES = (
    ROOT / "services" / "inbox_executor" / "src" / "executor_router.js",
    ROOT / "services" / "inbox_executor" / "src" / "router_cli.js",
    ROOT / "services" / "inbox_executor" / "src" / "agentic_executor.js",
)


class InboxExecutorE2ETests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if not self.node:
            self.skipTest("node unavailable")

    def test_node_entrypoints_parse(self):
        for path in NODE_FILES:
            proc = subprocess.run(
                [self.node, "--check", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            merged = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
            self.assertEqual(0, proc.returncode, f"{path}\n{merged}")

    def test_inbox_identity_and_router_e2e(self):
        proc = subprocess.run(
            [self.node, str(INBOX_E2E)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        merged = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        self.assertEqual(0, proc.returncode, merged)
        self.assertIn("EXECUTOR_IDENTITY_E2E_PASS", merged)


if __name__ == "__main__":
    unittest.main()

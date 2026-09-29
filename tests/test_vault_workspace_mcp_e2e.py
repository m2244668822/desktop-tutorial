import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
E2E = ROOT / "services" / "vault_workspace_mcp" / "src" / "e2e.js"


class VaultWorkspaceMCPE2ETests(unittest.TestCase):
    def test_node_e2e_covers_engineering_tools(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node unavailable")
        proc = subprocess.run(
            [node, str(E2E)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        merged = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        self.assertEqual(0, proc.returncode, merged)
        self.assertIn("E2E_PASS", merged)


if __name__ == "__main__":
    unittest.main()

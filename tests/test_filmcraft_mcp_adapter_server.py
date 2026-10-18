import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "tools" / "filmcraft_mcp_adapter.py"


class FilmCraftAdapterServerTests(unittest.TestCase):
    def _request(self, process, request_id, method, params):
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
                ensure_ascii=False,
            )
            + "\n"
        )
        process.stdin.flush()
        line = process.stdout.readline()
        self.assertTrue(line, "adapter server closed before responding")
        response = json.loads(line)
        self.assertEqual(request_id, response.get("id"))
        self.assertNotIn("error", response)
        return response.get("result", {})

    def _notify(self, process, method, params):
        process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": method, "params": params}, ensure_ascii=False)
            + "\n"
        )
        process.stdin.flush()

    def _tool_call(self, process, request_id, name, arguments):
        result = self._request(
            process,
            request_id,
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
                "_meta": {"whiteStudio": self.context(request_id)},
            },
        )
        content = result.get("content", [])
        self.assertTrue(content)
        return json.loads(content[0]["text"])

    @staticmethod
    def context(number):
        return {
            "task_id": "task-filmcraft-test",
            "run_id": f"run-filmcraft-test-{number}",
            "operation_id": f"op-filmcraft-test-{number}",
            "idempotency_key": f"idem-filmcraft-test-{number}",
            "capability": "disposable_write" if number in {4, 6, 9, 10} else "read",
            "project_id": "demo",
            "project_fingerprint": "sha256:filmcraft-demo",
        }

    def _error(self, process, request_id, method, params):
        process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n"
        )
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        self.assertEqual(request_id, response.get("id"))
        self.assertIn("error", response)
        return response["error"]["message"]

    def test_stdio_adapter_proxies_demo_and_preserves_undo_state(self):
        process = subprocess.Popen(
            [sys.executable, str(SERVER), "--demo"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            initialized = self._request(
                process,
                1,
                "initialize",
                {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
            )
            self.assertEqual("filmcraft-adapter", initialized["serverInfo"]["name"])
            self._notify(process, "notifications/initialized", {})
            tools = self._request(process, 2, "tools/list", {})
            names = {item["name"] for item in tools["tools"]}
            self.assertTrue({"project_inspect", "markers_add", "edit_undo", "state_snapshot"} <= names)
            self.assertIn(
                "schema_invalid:markers_add",
                self._error(
                    process,
                    9,
                    "tools/call",
                    {
                        "name": "markers_add",
                        "arguments": {},
                        "_meta": {"whiteStudio": self.context(9)},
                    },
                ),
            )

            before = self._tool_call(process, 3, "state_snapshot", {})
            added = self._tool_call(process, 4, "markers_add", {"seconds": 1.0, "name": "adapter-test"})
            self.assertIn("marker", added)
            self.assertTrue(added["success"])
            self.assertEqual("task-filmcraft-test", added["task_id"])
            self.assertTrue(added["before_state_hash"].startswith("sha256:"))
            self.assertTrue(added["after_state_hash"].startswith("sha256:"))
            after = self._tool_call(process, 5, "state_snapshot", {})
            self.assertNotEqual(before, after)

            undone = self._tool_call(process, 6, "edit_undo", {})
            self.assertEqual("Add Marker", undone["undone"])
            self.assertFalse(undone["undo_available"])
            restored = self._tool_call(process, 7, "state_snapshot", {})
            self.assertEqual(before, restored)

            replayed = self._tool_call(process, 4, "markers_add", {"seconds": 1.0, "name": "adapter-test"})
            self.assertEqual(added, replayed)

            conflict = self._error(
                process,
                10,
                "tools/call",
                {
                    "name": "markers_add",
                    "arguments": {"seconds": 2.0, "name": "different"},
                    "_meta": {"whiteStudio": self.context(4)},
                },
            )
            self.assertIn("idempotency_conflict", conflict)
        finally:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=5)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()

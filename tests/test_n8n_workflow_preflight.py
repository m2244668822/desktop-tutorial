import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "n8n_workflow_preflight.py"
SPEC = importlib.util.spec_from_file_location("n8n_workflow_preflight", MODULE_PATH)
n8n_workflow_preflight = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["n8n_workflow_preflight"] = n8n_workflow_preflight
SPEC.loader.exec_module(n8n_workflow_preflight)


class N8nWorkflowPreflightTests(unittest.TestCase):
    def test_xiaobian_workflow_blocks_activation_when_unsafe(self):
        old_which = n8n_workflow_preflight.shutil.which
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                spec = root / "workflow.json"
                db = root / "database.sqlite"
                spec.write_text(
                    json.dumps(
                        {
                            "id": "xiaobianVideo001",
                            "name": "Xiaobian Short Video Automation",
                            "active": False,
                            "nodes": [
                                {
                                    "name": "OpenAI TTS",
                                    "type": "n8n-nodes-base.openAi",
                                    "parameters": {"text": "hello"},
                                },
                                {
                                    "name": "FFmpeg Assembly",
                                    "type": "n8n-nodes-base.executeCommand",
                                    "parameters": {
                                        "command": "ffmpeg -i image.png -i audio.mp3 -vf 'drawtext=...' output.mp4"
                                    },
                                },
                                {
                                    "name": "Webhook Trigger",
                                    "type": "n8n-nodes-base.webhook",
                                    "parameters": {"httpMethod": "POST", "path": "video-script"},
                                },
                            ],
                            "settings": {},
                            "meta": {},
                        }
                    ),
                    encoding="utf-8",
                )
                con = sqlite3.connect(db)
                for table in ("workflow_entity", "credentials_entity", "execution_entity"):
                    con.execute(f"create table {table} (id text, name text, active integer)")
                con.execute(
                    "insert into workflow_entity (id, name, active) values (?, ?, ?)",
                    ("xiaobianVideo001", "Xiaobian Short Video Automation", 0),
                )
                con.commit()
                con.close()
                n8n_workflow_preflight.shutil.which = lambda _name: None

                payload = n8n_workflow_preflight.run_preflight(spec, db)

                codes = {issue["code"] for issue in payload["issues"]}
                self.assertFalse(payload["ok_for_activation"])
                self.assertEqual(payload["status"], "blocked_for_activation")
                self.assertIn("missing_node_credentials", codes)
                self.assertIn("n8n_database_has_no_credentials", codes)
                self.assertIn("placeholder_command", codes)
                self.assertIn("unsafe_relative_media_paths", codes)
                self.assertIn("ffmpeg_not_found", codes)
                self.assertIn("webhook_without_auth", codes)
                self.assertIn("missing_execution_timeout", codes)
                self.assertIn("missing_cost_controls", codes)
        finally:
            n8n_workflow_preflight.shutil.which = old_which


if __name__ == "__main__":
    unittest.main()

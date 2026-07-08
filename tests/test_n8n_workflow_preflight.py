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
        old_locate = n8n_workflow_preflight.locate_ffmpeg
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
                n8n_workflow_preflight.locate_ffmpeg = lambda *_args, **_kwargs: {
                    "found": False,
                    "source": "missing",
                    "path": "",
                    "configured_path": "",
                    "path_lookup": "",
                    "candidate_paths": [],
                }

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
                self.assertIn("n8n_database_workflow_stale", codes)
                remediation_codes = {item["code"] for item in payload["remediation_plan"]}
                self.assertIn("missing_node_credentials", remediation_codes)
                self.assertIn("n8n_database_has_no_credentials", remediation_codes)
                self.assertIn("ffmpeg_not_found", remediation_codes)
                self.assertIn("n8n_database_workflow_stale", remediation_codes)
                ffmpeg_plan = next(
                    item for item in payload["remediation_plan"] if item["code"] == "ffmpeg_not_found"
                )
                self.assertTrue(ffmpeg_plan["manual"])
                self.assertIn("brew install ffmpeg", ffmpeg_plan["macos"])
                self.assertIn("winget install Gyan.FFmpeg", ffmpeg_plan["windows"])
                self.assertIn("ready_for_activation", " ".join(payload["activation_sequence"]))
        finally:
            n8n_workflow_preflight.shutil.which = old_which
            n8n_workflow_preflight.locate_ffmpeg = old_locate

    def test_remediation_plan_deduplicates_same_issue_code_and_summary(self):
        issues = [
            n8n_workflow_preflight.Issue(
                "blocker",
                "ffmpeg_not_found",
                "ffmpeg is not available.",
                {"node": "FFmpeg Assembly"},
            ),
            n8n_workflow_preflight.Issue(
                "blocker",
                "ffmpeg_not_found",
                "ffmpeg is not available.",
                {"node": "Other FFmpeg Node"},
            ),
        ]

        plan = n8n_workflow_preflight.build_remediation_plan(issues)

        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["code"], "ffmpeg_not_found")

    def test_explicit_ffmpeg_path_satisfies_execute_command_probe(self):
        old_which = n8n_workflow_preflight.shutil.which
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ffmpeg = root / "ffmpeg.exe"
                ffmpeg.write_text("stub", encoding="utf-8")
                nodes = [
                    {
                        "name": "FFmpeg Assembly",
                        "type": "n8n-nodes-base.executeCommand",
                        "parameters": {
                            "command": (
                                "node -e \"const ffmpeg=process.env.FFMPEG_PATH||"
                                "process.env.XIAOBIAN_FFMPEG_PATH||'ffmpeg';"
                                "const root=process.env.XIAOBIAN_VIDEO_OUTPUT_DIR||"
                                "path.join(process.cwd(),'data','generated','xiaobian-video');"
                                "cp.spawnSync(ffmpeg,[]);\""
                            )
                        },
                    }
                ]
                n8n_workflow_preflight.shutil.which = lambda _name: None

                issues = n8n_workflow_preflight.audit_execute_commands(
                    nodes,
                    n8n_workflow_preflight.resolve_ffmpeg(str(ffmpeg)),
                )

                codes = {issue.code for issue in issues}
                self.assertNotIn("ffmpeg_not_found", codes)
                self.assertNotIn("missing_ffmpeg_path_override", codes)
        finally:
            n8n_workflow_preflight.shutil.which = old_which

    def test_db_contract_detects_hardened_import(self):
        contract = n8n_workflow_preflight.workflow_contract_snapshot(
            [
                {
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"authentication": "headerAuth"},
                },
                {
                    "type": "n8n-nodes-base.executeCommand",
                    "parameters": {
                        "command": (
                            "node -e \"const root=process.env.XIAOBIAN_VIDEO_OUTPUT_DIR||"
                            "path.join(process.cwd(),'data','generated','xiaobian-video');"
                            "const ffmpeg=process.env.FFMPEG_PATH||"
                            "process.env.XIAOBIAN_FFMPEG_PATH||'ffmpeg';\""
                        )
                    },
                },
            ],
            {"executionTimeout": 900},
            {"cost_controls": {"max": 1}, "error_policy": {"default": "fail_closed"}},
        )

        self.assertTrue(contract["webhook_auth"])
        self.assertTrue(contract["hardened_command"])
        self.assertTrue(contract["ffmpeg_path_env"])
        self.assertTrue(contract["ffmpeg_fallback_env"])
        self.assertFalse(contract["placeholder_command"])
        self.assertFalse(contract["relative_media_paths"])
        self.assertTrue(contract["execution_timeout"])
        self.assertTrue(contract["cost_controls"])
        self.assertTrue(contract["error_policy"])


if __name__ == "__main__":
    unittest.main()

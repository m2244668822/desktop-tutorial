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
                                    "name": "Gemini Parser",
                                    "type": "n8n-nodes-base.googleGemini",
                                    "parameters": {"prompt": "parse"},
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
                credential_plan = payload["credential_setup_plan"]
                self.assertEqual(credential_plan["status"], "needs_credentials")
                self.assertTrue(credential_plan["manual_secret_required"])
                self.assertEqual(credential_plan["credential_count"], 0)
                required_providers = {
                    item["provider"] for item in credential_plan["required_credentials"]
                }
                self.assertIn("OpenAI", required_providers)
                self.assertIn("Google Gemini", required_providers)
                self.assertIn("OpenAI TTS", json.dumps(credential_plan))
                self.assertIn("Gemini Parser", json.dumps(credential_plan))
                self.assertNotIn("sk-", json.dumps(credential_plan).lower())
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

    def test_credential_setup_plan_groups_nodes_by_provider(self):
        nodes = [
            {
                "name": "Gemini Parser",
                "type": "n8n-nodes-base.googleGemini",
                "parameters": {},
            },
            {
                "name": "DALL-E 3 Generator",
                "type": "n8n-nodes-base.openAi",
                "parameters": {},
            },
            {
                "name": "OpenAI TTS",
                "type": "n8n-nodes-base.openAi",
                "parameters": {},
            },
        ]
        db = {"ok": True, "counts": {"credentials_entity": 0}}

        plan = n8n_workflow_preflight.build_credential_setup_plan(
            nodes,
            db,
            {"id": "xiaobianVideo001"},
        )

        self.assertEqual(plan["status"], "needs_credentials")
        self.assertTrue(plan["manual_secret_required"])
        self.assertEqual(len(plan["required_credentials"]), 2)
        by_provider = {item["provider"]: item for item in plan["required_credentials"]}
        self.assertEqual(by_provider["OpenAI"]["credential_type"], "openAiApi")
        self.assertEqual(
            by_provider["OpenAI"]["nodes_needing_binding"],
            ["DALL-E 3 Generator", "OpenAI TTS"],
        )
        self.assertIsNone(by_provider["Google Gemini"]["credential_type"])
        self.assertIn(
            "googleGeminiApi",
            by_provider["Google Gemini"]["credential_type_candidates"],
        )
        self.assertEqual(len(plan["missing_bindings"]), 3)
        self.assertEqual(
            plan["workflow_url_hint"],
            "http://127.0.0.1:5678/workflow/xiaobianVideo001",
        )

    def test_db_workflow_credentials_satisfy_source_spec_missing_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "database.sqlite"
            con = sqlite3.connect(db)
            con.execute(
                "create table workflow_entity (id text, name text, active integer, nodes text, settings text, meta text)"
            )
            con.execute(
                "create table credentials_entity (id text, name text, data text, type text)"
            )
            con.execute("create table execution_entity (id text)")
            con.execute(
                "insert into credentials_entity (id, name, data, type) values (?, ?, ?, ?)",
                ("cred-openai", "OpenAI Prod", "encrypted", "openAiApi"),
            )
            con.execute(
                "insert into workflow_entity (id, name, active, nodes, settings, meta) values (?, ?, ?, ?, ?, ?)",
                (
                    "xiaobianVideo001",
                    "Xiaobian Short Video Automation",
                    0,
                    json.dumps(
                        [
                            {
                                "name": "OpenAI TTS",
                                "type": "n8n-nodes-base.openAi",
                                "credentials": {
                                    "openAiApi": {"id": "cred-openai", "name": "OpenAI Prod"}
                                },
                            }
                        ]
                    ),
                    "{}",
                    "{}",
                ),
            )
            con.commit()
            con.close()
            spec_nodes = [
                {
                    "name": "OpenAI TTS",
                    "type": "n8n-nodes-base.openAi",
                    "parameters": {"text": "hello"},
                }
            ]

            snapshot = n8n_workflow_preflight.db_snapshot(
                db,
                "xiaobianVideo001",
                "Xiaobian Short Video Automation",
            )
            issues = n8n_workflow_preflight.audit_credentials(spec_nodes, snapshot)
            plan = n8n_workflow_preflight.build_credential_setup_plan(
                snapshot["workflow_nodes"],
                snapshot,
                {"id": "xiaobianVideo001"},
                "n8n_database_workflow",
            )

            self.assertEqual([issue.code for issue in issues], [])
            self.assertEqual(plan["status"], "ready")
            self.assertEqual(plan["binding_source"], "n8n_database_workflow")
            self.assertEqual(snapshot["credential_types"]["openAiApi"], 1)
            self.assertNotIn("data", json.dumps(snapshot["credentials"]))

    def test_db_workflow_binding_must_reference_existing_credential(self):
        db = {
            "ok": True,
            "counts": {"credentials_entity": 1},
            "credentials": [{"id": "other", "name": "Other OpenAI", "type": "openAiApi"}],
            "workflow_nodes": [
                {
                    "name": "OpenAI TTS",
                    "type": "n8n-nodes-base.openAi",
                    "credentials": {"openAiApi": {"id": "missing", "name": "Deleted OpenAI"}},
                }
            ],
        }
        spec_nodes = [
            {
                "name": "OpenAI TTS",
                "type": "n8n-nodes-base.openAi",
                "parameters": {},
            }
        ]

        issues = n8n_workflow_preflight.audit_credentials(spec_nodes, db)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "credential_reference_missing")
        self.assertEqual(issues[0].evidence["binding_source"], "n8n_database_workflow")

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

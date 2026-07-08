import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from subprocess import CompletedProcess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "foundation_health_check.py"
SPEC = importlib.util.spec_from_file_location("foundation_health_check", MODULE_PATH)
foundation_health_check = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["foundation_health_check"] = foundation_health_check
SPEC.loader.exec_module(foundation_health_check)


class FoundationHealthCheckTests(unittest.TestCase):
    def test_workspace_context_allows_external_cwd_but_reports_it(self):
        old_root = foundation_health_check.ROOT
        old_run = foundation_health_check.run
        old_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "repo"
                external = Path(tmp) / "elsewhere"
                external.mkdir()
                for rel in (
                    "desktop_chat_app.py",
                    "templates/chat.html",
                    "tools/foundation_health_check.py",
                    "docs/dev/FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md",
                ):
                    path = root / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("ok", encoding="utf-8")

                foundation_health_check.ROOT = root
                foundation_health_check.run = lambda *args, **kwargs: CompletedProcess(
                    args=args[0],
                    returncode=0,
                    stdout=str(root) + "\n",
                    stderr="",
                )
                os.chdir(external)

                check = foundation_health_check.check_workspace_context()
                os.chdir(old_cwd)

                self.assertTrue(check.ok)
                self.assertEqual(check.status, "ready_external_cwd")
                self.assertFalse(check.detail["cwd_inside_root"])
        finally:
            os.chdir(old_cwd)
            foundation_health_check.ROOT = old_root
            foundation_health_check.run = old_run

    def test_workspace_context_fails_git_root_mismatch(self):
        old_root = foundation_health_check.ROOT
        old_run = foundation_health_check.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "repo"
                other = Path(tmp) / "other"
                for rel in (
                    "desktop_chat_app.py",
                    "templates/chat.html",
                    "tools/foundation_health_check.py",
                    "docs/dev/FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md",
                ):
                    path = root / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("ok", encoding="utf-8")
                other.mkdir()

                foundation_health_check.ROOT = root
                foundation_health_check.run = lambda *args, **kwargs: CompletedProcess(
                    args=args[0],
                    returncode=0,
                    stdout=str(other) + "\n",
                    stderr="",
                )

                check = foundation_health_check.check_workspace_context()

                self.assertFalse(check.ok)
                self.assertEqual(check.status, "git_root_mismatch")
        finally:
            foundation_health_check.ROOT = old_root
            foundation_health_check.run = old_run

    def test_write_report_records_overall_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            checks = [
                foundation_health_check.Check("one", True, "ready", {}),
                foundation_health_check.Check("two", False, "degraded", {"reason": "x"}),
            ]

            foundation_health_check.write_report(checks, path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual([row["name"] for row in payload["checks"]], ["one", "two"])
            self.assertIn("next_actions", payload)
            self.assertFalse(payload["attention_required"])
            self.assertEqual(payload["action_summary"]["count"], 0)

    def test_write_report_marks_attention_required_for_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            checks = [
                foundation_health_check.Check(
                    "ports",
                    False,
                    "degraded",
                    {
                        "5001": {"role": "main_web_gateway", "listening": False},
                    },
                )
            ]

            foundation_health_check.write_report(checks, path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["attention_required"])
            self.assertTrue(payload["action_summary"]["blocking_attention"])
            self.assertEqual(payload["action_summary"]["highest_priority"], "P1")
            self.assertEqual(payload["action_summary"]["by_priority"]["P1"], 1)

    def test_next_actions_include_n8n_remediation_plan(self):
        checks = [
            foundation_health_check.Check(
                "n8n_workflow_preflight",
                True,
                "blocked_for_activation",
                {
                    "report": {
                        "remediation_plan": [
                            {
                                "code": "ffmpeg_not_found",
                                "severity": "blocker",
                                "manual": True,
                                "summary": "Install FFmpeg and make sure ffmpeg is available on PATH.",
                                "windows": ["winget install Gyan.FFmpeg"],
                                "macos": ["brew install ffmpeg"],
                                "verify": "ffmpeg -version",
                                "evidence": {"node": "FFmpeg Assembly"},
                            }
                        ]
                    }
                },
            )
        ]

        actions = foundation_health_check.build_next_actions(checks)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["source"], "n8n_workflow_preflight")
        self.assertEqual(actions[0]["priority"], "P1")
        self.assertIn("FFmpeg", actions[0]["summary"])
        self.assertIn("winget install Gyan.FFmpeg", actions[0]["windows"])
        self.assertIn("brew install ffmpeg", actions[0]["macos"])
        self.assertEqual(actions[0]["evidence"]["code"], "ffmpeg_not_found")

    def test_next_actions_report_missing_runtime_ports(self):
        checks = [
            foundation_health_check.Check(
                "ports",
                False,
                "degraded",
                {
                    "5001": {"role": "main_web_gateway", "listening": False},
                    "5678": {"role": "n8n_editor", "listening": True},
                },
            )
        ]

        actions = foundation_health_check.build_next_actions(checks)

        self.assertEqual(actions[0]["source"], "ports")
        self.assertEqual(actions[0]["priority"], "P1")
        self.assertIn("5001:main_web_gateway", actions[0]["evidence"]["missing"])
        self.assertIn("runtime_service_controller.py start", " ".join(actions[0]["windows"]))

    def test_next_actions_include_runtime_dependency_doctor_items(self):
        checks = [
            foundation_health_check.Check(
                "runtime_dependencies",
                False,
                "attention_required",
                {
                    "next_actions": [
                        {
                            "source": "ffmpeg",
                            "status": "missing",
                            "summary": "Install FFmpeg",
                            "windows": ["winget install Gyan.FFmpeg"],
                            "macos": ["brew install ffmpeg"],
                            "verify": "ffmpeg -version",
                            "evidence": {"resolution": {"source": "missing"}},
                        }
                    ]
                },
            )
        ]

        actions = foundation_health_check.build_next_actions(checks)

        self.assertEqual(actions[0]["source"], "runtime_dependencies")
        self.assertEqual(actions[0]["priority"], "P1")
        self.assertEqual(actions[0]["summary"], "Install FFmpeg")
        self.assertEqual(actions[0]["evidence"]["source"], "ffmpeg")

    def test_runtime_service_controller_check_reads_status_report(self):
        old_root = foundation_health_check.ROOT
        old_run = foundation_health_check.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                report = root / "reports" / "runtime_service_controller_health_latest.json"
                foundation_health_check.ROOT = root

                def fake_run(*args, **kwargs):
                    report.parent.mkdir(parents=True)
                    report.write_text(
                        json.dumps(
                            {
                                "ok": True,
                                "status": "ready",
                                "results": [
                                    {"name": "web", "ok": True, "status": "ready"},
                                ],
                                "next_actions": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    return CompletedProcess(
                        args=args[0],
                        returncode=0,
                        stdout="ready",
                        stderr="",
                    )

                foundation_health_check.run = fake_run

                check = foundation_health_check.check_runtime_service_controller()

                self.assertTrue(check.ok)
                self.assertEqual(check.status, "ready")
                self.assertEqual(check.detail["report"]["results"][0]["name"], "web")
        finally:
            foundation_health_check.ROOT = old_root
            foundation_health_check.run = old_run

    def test_next_actions_include_runtime_service_controller_items(self):
        checks = [
            foundation_health_check.Check(
                "runtime_service_controller",
                False,
                "attention_required",
                {
                    "report": {
                        "next_actions": [
                            {
                                "source": "openclaw",
                                "status": "governance_required",
                                "summary": "Approve and start OpenClaw Gateway.",
                                "governed": True,
                                "controller_command": [
                                    "python",
                                    "tools/runtime_service_controller.py",
                                    "start",
                                    "--components",
                                    "openclaw",
                                    "--allow-openclaw-mutation",
                                ],
                                "evidence": {"ports": {"18789": False}},
                            }
                        ]
                    }
                },
            )
        ]

        actions = foundation_health_check.build_next_actions(checks)

        self.assertEqual(actions[0]["source"], "runtime_service_controller")
        self.assertEqual(actions[0]["priority"], "P1")
        self.assertIn("--allow-openclaw-mutation", actions[0]["windows"][0])
        self.assertTrue(actions[0]["evidence"]["governed"])

    def test_knowledge_hub_requires_ready_indexes(self):
        old_root = foundation_health_check.ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                hub = root / "data" / "knowledge_hub"
                hub.mkdir(parents=True)
                (hub / "manifest.json").write_text(
                    json.dumps(
                        {
                            "chatgpt_database_ready": True,
                            "sqlite_ready": True,
                            "faiss_ready": True,
                            "total_items": 3,
                        }
                    ),
                    encoding="utf-8",
                )
                foundation_health_check.ROOT = root

                check = foundation_health_check.check_knowledge_hub()

                self.assertTrue(check.ok)
                self.assertEqual(check.status, "ready")
                self.assertEqual(check.detail["total_items"], 3)
        finally:
            foundation_health_check.ROOT = old_root

    def test_n8n_health_distinguishes_empty_workflow_db(self):
        old_db = foundation_health_check.N8N_DB
        old_http_get = foundation_health_check.http_get
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "database.sqlite"
                con = sqlite3.connect(db)
                for table in (
                    "workflow_entity",
                    "credentials_entity",
                    "execution_entity",
                    "webhook_entity",
                ):
                    con.execute(f"create table {table} (id text)")
                con.commit()
                con.close()
                foundation_health_check.N8N_DB = db
                foundation_health_check.http_get = lambda *args, **kwargs: {
                    "ok": True,
                    "status_code": 200,
                    "data": {"status": "ok"},
                    "error": "",
                }

                check = foundation_health_check.check_n8n()

                self.assertTrue(check.ok)
                self.assertEqual(check.status, "degraded")
                self.assertEqual(check.detail["counts"]["workflow_entity"], 0)
        finally:
            foundation_health_check.N8N_DB = old_db
            foundation_health_check.http_get = old_http_get

    def test_frontend_static_contract_requires_mobile_layout(self):
        old_root = foundation_health_check.ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                template = root / "templates" / "chat.html"
                template.parent.mkdir(parents=True)
                html = (ROOT / "templates" / "chat.html").read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                template.write_text(
                    html.replace("@media (max-width: 640px)", "@media (max-width: 641px)"),
                    encoding="utf-8",
                )
                foundation_health_check.ROOT = root

                check = foundation_health_check.check_frontend_static_contract()

                self.assertFalse(check.ok)
                self.assertEqual(check.status, "contract_drift")
                self.assertIn("@media (max-width: 640px)", check.detail["missing"])
        finally:
            foundation_health_check.ROOT = old_root

    def test_frontend_static_contract_rejects_mojibake_text(self):
        old_root = foundation_health_check.ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                template = root / "templates" / "chat.html"
                template.parent.mkdir(parents=True)
                html = (ROOT / "templates" / "chat.html").read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                template.write_text(
                    html.replace("尚未載入 OpenClaw 狀態", "撠頛 OpenClaw 狀態"),
                    encoding="utf-8",
                )
                foundation_health_check.ROOT = root

                check = foundation_health_check.check_frontend_static_contract()

                self.assertFalse(check.ok)
                self.assertEqual(check.status, "contract_drift")
                self.assertIn("尚未載入 OpenClaw 狀態", check.detail["missing"])
                self.assertIn("撠", check.detail["mojibake"])
                self.assertTrue(check.detail["private_use_codepoints"])
        finally:
            foundation_health_check.ROOT = old_root

    def test_gateway_surfaces_openclaw_stopped_warning(self):
        old_http_get = foundation_health_check.http_get
        try:
            def fake_http_get(path, port=5001, timeout=5):
                if path == "/api/get_status":
                    return {
                        "ok": True,
                        "status_code": 200,
                        "data": {
                            "monitor": {
                                "openclaw": {
                                    "installed": True,
                                    "daemon_running": False,
                                    "daemon_state": "stopped",
                                }
                            }
                        },
                        "error": "",
                    }
                return {"ok": True, "status_code": 200, "data": {"ok": True}, "error": ""}

            foundation_health_check.http_get = fake_http_get

            check = foundation_health_check.check_gateway()

            self.assertTrue(check.ok)
            self.assertEqual(check.status, "ready_with_openclaw_stopped")
        finally:
            foundation_health_check.http_get = old_http_get

    def test_openclaw_runtime_ready_when_local_execution_supported(self):
        from core import openclaw_bridge

        old_detect = openclaw_bridge.detect_openclaw_status
        try:
            openclaw_bridge.detect_openclaw_status = lambda _root: {
                "installed": True,
                "health": "ready",
                "local_execution": {
                    "supported": True,
                    "criteria": {
                        "cli_installed": True,
                        "gateway_listening": True,
                        "gateway_health_ok": True,
                    },
                },
            }

            check = foundation_health_check.check_openclaw_runtime()

            self.assertTrue(check.ok)
            self.assertEqual(check.status, "ready")
            self.assertTrue(check.detail["local_execution"]["supported"])
        finally:
            openclaw_bridge.detect_openclaw_status = old_detect

    def test_next_actions_include_openclaw_local_execution_gap(self):
        checks = [
            foundation_health_check.Check(
                "openclaw_runtime",
                True,
                "governed_stopped",
                {
                    "installed": True,
                    "health": "governed_stopped",
                    "gateway": {"listening": False, "health_ok": False},
                    "local_execution": {
                        "supported": False,
                        "criteria": {
                            "cli_installed": True,
                            "gateway_listening": False,
                            "gateway_health_ok": False,
                        },
                    },
                },
            )
        ]

        actions = foundation_health_check.build_next_actions(checks)

        self.assertEqual(actions[0]["source"], "openclaw_runtime")
        self.assertEqual(actions[0]["priority"], "P1")
        self.assertIn("OpenClaw Gateway", actions[0]["summary"])
        self.assertIn("gateway_listening", actions[0]["evidence"]["criteria"])

    def test_browser_smoke_auto_skips_missing_browser(self):
        old_root = foundation_health_check.ROOT
        old_run = foundation_health_check.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                reports = root / "reports"
                reports.mkdir()
                (reports / "chat_shell_browser_smoke_latest.json").write_text(
                    json.dumps({"ok": False, "status": "browser_not_found"}),
                    encoding="utf-8",
                )
                foundation_health_check.ROOT = root
                foundation_health_check.run = lambda *args, **kwargs: CompletedProcess(
                    args=args[0],
                    returncode=1,
                    stdout="[FAIL] browser_not_found",
                    stderr="",
                )

                check = foundation_health_check.check_browser_smoke("auto")

                self.assertTrue(check.ok)
                self.assertEqual(check.status, "skipped_browser_not_found")
        finally:
            foundation_health_check.ROOT = old_root
            foundation_health_check.run = old_run

    def test_browser_smoke_required_fails_missing_browser(self):
        old_root = foundation_health_check.ROOT
        old_run = foundation_health_check.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                reports = root / "reports"
                reports.mkdir()
                (reports / "chat_shell_browser_smoke_latest.json").write_text(
                    json.dumps({"ok": False, "status": "browser_not_found"}),
                    encoding="utf-8",
                )
                foundation_health_check.ROOT = root
                foundation_health_check.run = lambda *args, **kwargs: CompletedProcess(
                    args=args[0],
                    returncode=1,
                    stdout="[FAIL] browser_not_found",
                    stderr="",
                )

                check = foundation_health_check.check_browser_smoke("required")

                self.assertFalse(check.ok)
                self.assertEqual(check.status, "browser_not_found")
        finally:
            foundation_health_check.ROOT = old_root
            foundation_health_check.run = old_run

    def test_n8n_workflow_preflight_inventory_allows_activation_blockers(self):
        old_root = foundation_health_check.ROOT
        old_run = foundation_health_check.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                reports = root / "reports"
                reports.mkdir()
                (reports / "n8n_workflow_preflight_latest.json").write_text(
                    json.dumps(
                        {
                            "ok_for_activation": False,
                            "status": "blocked_for_activation",
                            "blocker_count": 3,
                            "issues": [],
                        }
                    ),
                    encoding="utf-8",
                )
                foundation_health_check.ROOT = root
                foundation_health_check.run = lambda *args, **kwargs: CompletedProcess(
                    args=args[0],
                    returncode=0,
                    stdout="status: blocked_for_activation",
                    stderr="",
                )

                check = foundation_health_check.check_n8n_workflow_preflight()

                self.assertTrue(check.ok)
                self.assertEqual(check.status, "blocked_for_activation")
        finally:
            foundation_health_check.ROOT = old_root
            foundation_health_check.run = old_run


if __name__ == "__main__":
    unittest.main()

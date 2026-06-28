import importlib.util
import json
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

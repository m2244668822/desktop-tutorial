import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SERVER = (ROOT / "core" / "web_server.py").read_text(encoding="utf-8-sig")
DESKTOP_APP = (ROOT / "desktop_chat_app.py").read_text(encoding="utf-8-sig")
CHATGPT_SERVER = (ROOT / "chatgpt_server.py").read_text(encoding="utf-8-sig")
STACK_MANAGER = (ROOT / "tools" / "manage_perob_stack.sh").read_text(encoding="utf-8")
HTTPS_PROXY = (ROOT / "tools" / "https_local_proxy.py").read_text(encoding="utf-8")
AEG_WRITER = (ROOT / "tools" / "write_aeg_shared_report.py").read_text(encoding="utf-8")


class PerobMainlineHealthContractTests(unittest.TestCase):
    def test_web_server_exposes_readiness_and_topology_routes(self):
        for route in [
            "/health/live",
            "/health/ready",
            "/api/runtime/topology",
            "/api/openclaw/status",
        ]:
            self.assertIn(route, WEB_SERVER)
        self.assertIn("def do_HEAD(self):", WEB_SERVER)

    def test_rerun_route_is_wired_from_http_to_runtime(self):
        self.assertIn('route_path == "/api/rerun_workflow_step"', WEB_SERVER)
        self.assertIn("server_instance.bridge.rerun_workflow_step(", WEB_SERVER)
        self.assertIn("rerun_task_step(", DESKTOP_APP)

    def test_background_threads_use_safe_session_cleanup(self):
        self.assertIn("def _remove_db_session_safely():", CHATGPT_SERVER)
        self.assertGreaterEqual(CHATGPT_SERVER.count("_remove_db_session_safely()"), 4)

    def test_stack_manager_uses_single_web_entry(self):
        self.assertNotIn("5002", STACK_MANAGER)
        self.assertIn("/health/ready", STACK_MANAGER)
        self.assertIn("PEROB_USE_LAUNCHAGENT", STACK_MANAGER)

    def test_https_proxy_recalculates_content_length_once(self):
        self.assertIn('"content-length"', HTTPS_PROXY)
        self.assertIn('self.send_header("Content-Length", str(len(data)))', HTTPS_PROXY)

    def test_repository_has_full_verification_entrypoint(self):
        self.assertTrue((ROOT / "tools" / "run_full_verification.sh").exists())

    def test_runtime_aeg_report_does_not_dirty_git_snapshot(self):
        self.assertIn('RUNTIME_OUT = RUNTIME_REPORTS_DIR / "AEG_SHARED_REPORT_LATEST.md"', AEG_WRITER)
        self.assertIn('CANONICAL_OUT = REPORTS_DIR / "AEG_SHARED_REPORT.md"', AEG_WRITER)
        self.assertIn('"--canonical"', AEG_WRITER)
        self.assertIn("out = CANONICAL_OUT if args.canonical else RUNTIME_OUT", AEG_WRITER)


if __name__ == "__main__":
    unittest.main()

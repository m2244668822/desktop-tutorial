import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SERVER = (ROOT / "core" / "web_server.py").read_text(encoding="utf-8-sig")
DESKTOP_APP = (ROOT / "desktop_chat_app.py").read_text(encoding="utf-8-sig")
CHATGPT_SERVER = (ROOT / "chatgpt_server.py").read_text(encoding="utf-8-sig")
STACK_MANAGER = (ROOT / "tools" / "manage_perob_stack.sh").read_text(encoding="utf-8")


class PerobMainlineHealthContractTests(unittest.TestCase):
    def test_web_server_exposes_readiness_and_topology_routes(self):
        for route in [
            "/health/live",
            "/health/ready",
            "/api/runtime/topology",
            "/api/openclaw/status",
        ]:
            self.assertIn(route, WEB_SERVER)

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


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SERVER = (ROOT / "core" / "web_server.py").read_text(encoding="utf-8-sig")
DESKTOP_APP = (ROOT / "desktop_chat_app.py").read_text(encoding="utf-8-sig")
CHATGPT_SERVER = (ROOT / "chatgpt_server.py").read_text(encoding="utf-8-sig")
STACK_MANAGER = (ROOT / "tools" / "manage_perob_stack.sh").read_text(encoding="utf-8")
LAUNCHAGENT_INSTALLER = (ROOT / "tools" / "install_perob_launchagents.sh").read_text(encoding="utf-8")
START_WEB_5001 = (ROOT / "tools" / "start_web_server_5001.sh").read_text(encoding="utf-8")
FULL_VERIFICATION = (ROOT / "tools" / "run_full_verification.sh").read_text(encoding="utf-8")
HTTPS_PROXY = (ROOT / "tools" / "https_local_proxy.py").read_text(encoding="utf-8")
AEG_WRITER = (ROOT / "tools" / "write_aeg_shared_report.py").read_text(encoding="utf-8")
BACKEND_LAUNCHER = ROOT / "tools" / "launch_trevor_backend.py"


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

    def test_readiness_exposes_memory_autosave_and_aeg_training(self):
        self.assertIn("memory_autosave", WEB_SERVER)
        self.assertIn("aeg_training", WEB_SERVER)
        self.assertIn("get_memory_autosave_status", DESKTOP_APP)
        self.assertIn("get_aeg_training_status", DESKTOP_APP)

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

    def test_runtime_launchers_prefer_python312_before_bare_python3(self):
        for name, text in {
            "manage_perob_stack.sh": STACK_MANAGER,
            "install_perob_launchagents.sh": LAUNCHAGENT_INSTALLER,
            "start_web_server_5001.sh": START_WEB_5001,
            "run_full_verification.sh": FULL_VERIFICATION,
        }.items():
            self.assertIn("command -v python3.12", text, name)
            self.assertIn("command -v python3.11", text, name)
            self.assertLess(
                text.index("command -v python3.12"),
                text.index("command -v python3 || true"),
                name,
            )

    def test_runtime_launchers_prefer_managed_python312_and_private_https(self):
        for name, text in {
            "manage_perob_stack.sh": STACK_MANAGER,
            "install_perob_launchagents.sh": LAUNCHAGENT_INSTALLER,
        }.items():
            self.assertIn('.python-installations/cpython-3.12', text, name)
            self.assertIn('PEROB_HTTPS_LISTEN_HOST', text, name)
            self.assertIn('127.0.0.1', text, name)

    def test_backend_launchagent_uses_trusted_credential_staging_wrapper(self):
        self.assertTrue(BACKEND_LAUNCHER.exists())
        self.assertIn('launch_trevor_backend.py', LAUNCHAGENT_INSTALLER)
        self.assertIn('CREDENTIALS_DIRECTORY', BACKEND_LAUNCHER.read_text(encoding='utf-8'))

    def test_backend_launchagent_propagates_safe_provider_runtime_flags(self):
        for name, value in {
            "TREVOR_GEMINI_FREE_TIER_CONFIRMED": "true",
            "TREVOR_GROQ_FREE_TIER_CONFIRMED": "true",
            "TREVOR_WEB_SEARCH_ENABLED": "true",
            "TREVOR_DELIBERATION_ROLLOUT": "shadow",
        }.items():
            self.assertIn(f"<key>{name}</key><string>{value}</string>", LAUNCHAGENT_INSTALLER)
            self.assertIn(f'--env "{name}={value}"', STACK_MANAGER)

    def test_full_verification_disables_interactive_keychain_access(self):
        self.assertIn("export TREVOR_DISABLE_KEYCHAIN=true", FULL_VERIFICATION)

    def test_https_proxy_recalculates_content_length_once(self):
        self.assertIn('"content-length"', HTTPS_PROXY)
        self.assertIn('self._safe_send_response(', HTTPS_PROXY)
        self.assertIn("len(data)", HTTPS_PROXY)

    def test_repository_has_full_verification_entrypoint(self):
        self.assertTrue((ROOT / "tools" / "run_full_verification.sh").exists())


    def test_https_proxy_uses_safe_response_writes(self):
        self.assertIn("def _safe_send_response", HTTPS_PROXY)
        self.assertIn("def _safe_write", HTTPS_PROXY)
        for recoverable in ["BrokenPipeError", "ConnectionResetError", "ssl.SSLError"]:
            self.assertIn(recoverable, HTTPS_PROXY)

    def test_openclaw_task_route_and_optional_n8n_contracts(self):
        self.assertIn('route_path == "/api/openclaw/task"', WEB_SERVER)
        self.assertIn("forwarding_mode", WEB_SERVER)
        self.assertIn("openclaw_forwarding_degraded", WEB_SERVER)
        self.assertIn('"n8n"', WEB_SERVER)

    def test_agent_collaboration_review_generator_exists(self):
        generator = ROOT / "tools" / "generate_agent_collaboration_review.py"
        self.assertTrue(generator.exists())
        text = generator.read_text(encoding="utf-8")
        for phrase in ["智能體協作", "錯誤選擇", "補救結果", "下次避免重犯規則"]:
            self.assertIn(phrase, text)

    def test_runtime_aeg_report_does_not_dirty_git_snapshot(self):
        self.assertIn('RUNTIME_OUT = RUNTIME_REPORTS_DIR / "AEG_SHARED_REPORT_LATEST.md"', AEG_WRITER)
        self.assertIn('CANONICAL_OUT = REPORTS_DIR / "AEG_SHARED_REPORT.md"', AEG_WRITER)
        self.assertIn('"--canonical"', AEG_WRITER)
        self.assertIn("out = CANONICAL_OUT if args.canonical else RUNTIME_OUT", AEG_WRITER)


if __name__ == "__main__":
    unittest.main()

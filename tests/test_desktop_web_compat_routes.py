import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / 'desktop_chat_app.py'
WEB_SERVER_PATH = ROOT / 'core' / 'web_server.py'
CHAT_TEMPLATE_PATH = ROOT / 'templates' / 'chat.html'


class DesktopWebCompatRoutesTests(unittest.TestCase):
    def setUp(self):
        self.server = SERVER_PATH.read_text(encoding='utf-8')
        self.web_server = WEB_SERVER_PATH.read_text(encoding='utf-8')
        self.chat = CHAT_TEMPLATE_PATH.read_text(encoding='utf-8')

    def test_frontend_calls_compat_routes(self):
        for route in [
            '/chat/agent',
            '/agent/tasks/summary',
            '/agent/tasks?limit=30&compact=1',
            '/archive/export',
            '/archive/cleanup',
            '/archive/list',
            '/api/orchestrator/status',
            '/trace/learning-status',
        ]:
            self.assertIn(route, self.chat)

    def test_backend_exposes_matching_routes(self):
        for route in [
            '/chat/agent',
            '/agent/tasks/summary',
            '/agent/tasks',
            '/archive/export',
            '/archive/cleanup',
            '/archive/list',
            '/api/orchestrator/status',
            '/trace/learning-status',
        ]:
            self.assertIn(route, self.web_server)

    def test_backend_has_compatibility_helpers(self):
        for token in [
            'task_summary_payload(server_instance.workspace_path)',
            'task_items_payload(',
            'status=""',
            'limit=30',
            'server_instance.bridge.send_message(',
            'server_instance.bridge.get_api_onboarding_info()',
            'provider_catalog',
            'chat_preferred_provider',
        ]:
            self.assertIn(token, self.web_server)


if __name__ == '__main__':
    unittest.main()

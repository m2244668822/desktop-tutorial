import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / 'desktop_chat_app.py'
CHAT_TEMPLATE_PATH = ROOT / 'templates' / 'chat.html'


class DesktopWebCompatRoutesTests(unittest.TestCase):
    def setUp(self):
        self.server = SERVER_PATH.read_text(encoding='utf-8')
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
            '/agent/xiaobian/video-task',
            '/system/communication/status',
        ]:
            self.assertIn(route, self.server)

    def test_backend_has_compatibility_helpers(self):
        for token in [
            'def _provider_status_payload()',
            'def _conversation_records(',
            'def _tasks_summary_payload()',
            'def _tasks_items_payload(',
            'def _chat_agent_payload(',
            'def _video_task_payload(',
            'provider_catalog',
            'chat_preferred_provider',
        ]:
            self.assertIn(token, self.server)


if __name__ == '__main__':
    unittest.main()

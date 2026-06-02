import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / 'templates' / 'chat.html'
SERVER_PATH = ROOT / 'desktop_chat_app.py'


class ChatClickEventsTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding='utf-8')
        self.server = SERVER_PATH.read_text(encoding='utf-8')

    def test_inline_click_handlers_reference_existing_functions(self):
        handlers = set(re.findall(r'^(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(', self.html, re.M))
        inline_calls = re.findall(r'onclick="([A-Za-z_][A-Za-z0-9_]*)\(', self.html)
        missing = sorted({name for name in inline_calls if name not in handlers})
        self.assertEqual([], missing)

    def test_dynamic_click_handlers_reference_existing_functions(self):
        for fn in [
            'removeAttach',
            'triggerLearn',
            'filterTasks',
            'selectAgent',
            'openLightbox',
            'submitQuickReply',
            'usePrompt',
        ]:
            self.assertIn(f'function {fn}', self.html)

    def test_agent_aliases_route_legacy_manager_to_proclaimer(self):
        self.assertIn('dispatcher: "proclaimer"', self.html)
        self.assertIn('manager: "proclaimer"', self.html)
        self.assertNotIn('general: "dispatcher"', self.html)
        self.assertNotIn('manager: "dispatcher"', self.html)
        self.assertIn("selectAgent('general','🤖','通用')", self.html)

    def test_backend_frontend_agent_keys_match_sidebar_entries(self):
        for token in [
            '"總管": "proclaimer"',
            '"申言者": "proclaimer"',
            '"帽子": "whitehat"',
        ]:
            self.assertIn(token, self.server)


if __name__ == '__main__':
    unittest.main()

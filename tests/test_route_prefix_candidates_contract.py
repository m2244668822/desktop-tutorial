import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_TEMPLATE = ROOT / 'templates' / 'chat.html'
WEB_SERVER = ROOT / 'core' / 'web_server.py'


class RoutePrefixCandidatesContractTests(unittest.TestCase):
    def test_frontend_has_route_candidates_retry(self):
        text = CHAT_TEMPLATE.read_text(encoding='utf-8')
        for token in [
            'function _buildRouteCandidates(url)',
            'const hasPerobBase = /\\/perob\\/?$/i.test(base);',
            'const withPerob = (path) =>',
            'const withoutPerob = (path) =>',
            'const routeCandidates = _buildRouteCandidates(url);',
        ]:
            self.assertIn(token, text)

    def test_backend_has_chat_agent_compat_routes(self):
        text = WEB_SERVER.read_text(encoding='utf-8')
        route_block_start = text.index('if route_path in {"/api/send_message"')
        route_block = text[route_block_start: route_block_start + 240]
        for route in [
            '"/api/send_message"',
            '"/api/send_message/"',
            '"/chat/agent"',
            '"/chat/agent/"',
        ]:
            self.assertIn(route, route_block)
        self.assertIn('if route_path in {"/chat/agent", "/chat/agent/"}:', text)


if __name__ == '__main__':
    unittest.main()

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / 'templates' / 'chat.html'


class ChatFrontendApiCleanupTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding='utf-8')

    def test_debug_ingest_is_configurable_not_hardcoded(self):
        self.assertIn('const DEBUG_INGEST_URL = window.__DEBUG_INGEST_URL__ || "";', self.html)
        self.assertNotIn('http://127.0.0.1:7861/ingest/', self.html)

    def test_agent_aliases_cover_old_backend_keys(self):
        for token in [
            'manager: "dispatcher"',
            'learner: "researcher"',
            'proclaimer: "prophet"',
            'whitehat: "hat"',
        ]:
            self.assertIn(token, self.html)
        self.assertNotIn('general: "dispatcher"', self.html)

    def test_polling_bootstrap_is_grouped(self):
        self.assertIn('function bootstrapPolling()', self.html)
        self.assertIn('bootstrapPolling();', self.html)
        for token in [
            'fetchKALStatus(true);',
            'fetchHistory(true);',
            'fetchTasksSummary(true);',
            'fetchProviderStatus(true);',
            'fetchArchiveList();',
        ]:
            self.assertIn(token, self.html)

    def test_ui_helpers_reduce_inline_dom_noise(self):
        for token in [
            'const $ = (id) => document.getElementById(id);',
            'function openExternal(url)',
            'function triggerFilePicker()',
            'function showHubPanel(panelId)',
            'function syncModelHeader()',
        ]:
            self.assertIn(token, self.html)

    def test_inline_actions_use_named_helpers(self):
        for token in [
            "onclick=\"showHubPanel('kalPanel')\"",
            "onclick=\"showHubPanel('tasksPanel')\"",
            "onclick=\"triggerFilePicker()\"",
            "onclick=\"openExternal('https://claude.ai')\"",
        ]:
            self.assertIn(token, self.html)

    def test_topbar_logo_no_longer_depends_on_missing_static_asset(self):
        self.assertIn('<svg class="tb-logo"', self.html)
        self.assertNotIn('/static/branding/topbar-logo.png', self.html)


if __name__ == '__main__':
    unittest.main()

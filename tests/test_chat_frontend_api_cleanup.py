import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / 'templates' / 'chat_shell.html'


class ChatFrontendApiCleanupTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding='utf-8')

    def test_debug_ingest_is_configurable_not_hardcoded(self):
        self.assertIn('const DEBUG_INGEST_URL = window.__DEBUG_INGEST_URL__ || "";', self.html)
        self.assertNotIn('http://127.0.0.1:7861/ingest/', self.html)

    def test_agent_aliases_cover_old_backend_keys(self):
        for token in [
            'dispatcher: "trevor"',
            'manager: "trevor"',
            'learner: "trevor"',
            'prophet: "trevor"',
            'hat: "trevor"',
        ]:
            self.assertIn(token, self.html)
        self.assertIn('return normalized === "trevor" ? "trevor"', self.html)

    def test_polling_bootstrap_is_grouped(self):
        self.assertIn('function bootstrapPolling()', self.html)
        self.assertIn('bootstrapPolling();', self.html)
        for token in [
            'fetchHistory(true);',
            'fetchTasksSummary(true);',
            'fetchProviderStatus(true);',
            'fetchArchiveList();',
        ]:
            self.assertIn(token, self.html)

    def test_snapshot_does_not_overwrite_filtered_task_view(self):
        self.assertIn('if (_tasksFilter) {', self.html)
        self.assertIn('fetchTasksSummary(true);', self.html)
        self.assertIn('renderTasksPanel(tasks.summary || {}, tasks.items || []);', self.html)

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
            "onclick=\"showHubPanel('tasksPanel')\"",
            "onclick=\"triggerFilePicker()\"",
        ]:
            self.assertIn(token, self.html)

    def test_primary_chat_does_not_expose_dead_external_model_card(self):
        self.assertNotIn("onclick=\"openExternal('https://claude.ai')\"", self.html)

    def test_topbar_logo_no_longer_depends_on_missing_static_asset(self):
        self.assertIn('<svg class="tb-logo"', self.html)
        self.assertNotIn('/static/branding/topbar-logo.png', self.html)

    def test_chat_shell_removes_legacy_kal_ui_and_polling(self):
        for token in [
            '🔬 KAL 學習',
            'KAL 自主學習迴圈',
            '學習系統狀態',
            'fetchKALStatus',
            'renderKAL',
            'mon-kal',
            'mon-distill',
            'mon-valid',
        ]:
            self.assertNotIn(token, self.html)

    def test_chat_shell_catalog_shows_current_openrouter_chat_model(self):
        self.assertIn("id=\"mc-openrouter\"", self.html)
        self.assertIn("startChat('openrouter','OpenRouter')", self.html)
        self.assertIn("nvidia/nemotron-3-ultra-550b-a55b:free", self.html)
        for token in ["id=\"mc-nvidia\"", "id=\"mc-openai\"", "id=\"mc-gemini\"", "id=\"mc-groq\""]:
            self.assertNotIn(token, self.html)


if __name__ == '__main__':
    unittest.main()

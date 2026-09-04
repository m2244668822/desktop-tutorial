import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_SHELL = ROOT / "templates" / "chat_shell.html"


class ChatShellRuntimeTemplateTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_SHELL.read_text(encoding="utf-8")

    def test_runtime_template_uses_inline_topbar_logo(self):
        self.assertIn('<svg class="tb-logo"', self.html)
        self.assertNotIn('/static/branding/topbar-logo.png', self.html)

    def test_runtime_template_uses_single_send_and_scoped_escape_handling(self):
        for token in [
            'function handleMessageKeydown(e)',
            'msgInput.addEventListener("keydown", handleMessageKeydown);',
            'function handleGlobalEscape(e)',
            'window.addEventListener("keydown", handleGlobalEscape, true);',
            'toggleAdvancedSettings(false);',
        ]:
            self.assertIn(token, self.html)

        for legacy_token in [
            'function cancelPendingSendConfirmation()',
            'pendingSendConfirmation',
            'msgInput.addEventListener("blur", cancelPendingSendConfirmation);',
        ]:
            self.assertNotIn(legacy_token, self.html)


if __name__ == "__main__":
    unittest.main()

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

    def test_runtime_template_escape_handlers_cover_input_and_global_scope(self):
        for token in [
            'function cancelPendingSendConfirmation()',
            'function handleMessageKeydown(e)',
            'msgInput.addEventListener("keydown", handleMessageKeydown);',
            'msgInput.addEventListener("keyup", e => {',
            'function handleGlobalEscape(e)',
            'window.addEventListener("keydown", handleGlobalEscape, true);',
            'window.addEventListener("keyup", handleGlobalEscape, true);',
            'document.addEventListener("keydown", handleGlobalEscape, true);',
            'document.addEventListener("keyup", handleGlobalEscape, true);',
            'msgInput.addEventListener("blur", cancelPendingSendConfirmation);',
        ]:
            self.assertIn(token, self.html)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / 'templates' / 'chat.html'


class ChatKeyboardEventsTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding='utf-8')

    def test_named_keyboard_handlers_exist(self):
        self.assertIn('function handleMessageKeydown(e)', self.html)
        self.assertIn('function handleMessageInput()', self.html)
        self.assertIn('msgInput.addEventListener("keydown", handleMessageKeydown);', self.html)
        self.assertIn('msgInput.addEventListener("input", handleMessageInput);', self.html)

    def test_enter_sends_only_when_not_shift_and_not_composing(self):
        self.assertIn('if (e.key === "Enter" && !e.shiftKey && !state.composing)', self.html)
        self.assertIn('e.preventDefault();', self.html)
        self.assertIn('confirmAndSendMessage();', self.html)

    def test_escape_clears_pending_confirmation(self):
        self.assertIn('if (e.key === "Escape") {', self.html)
        self.assertIn('function cancelPendingSendConfirmation()', self.html)
        self.assertIn('cancelPendingSendConfirmation();', self.html)
        self.assertIn('function handleGlobalEscape(e)', self.html)
        self.assertIn('if (e.key !== "Escape") return;', self.html)
        self.assertIn('msgInput.addEventListener("keyup", e => {', self.html)
        self.assertIn('msgInput.addEventListener("blur", cancelPendingSendConfirmation);', self.html)
        self.assertIn('window.addEventListener("keydown", handleGlobalEscape, true);', self.html)
        self.assertIn('window.addEventListener("keyup", handleGlobalEscape, true);', self.html)
        self.assertIn('document.addEventListener("keydown", handleGlobalEscape, true);', self.html)
        self.assertIn('document.addEventListener("keyup", handleGlobalEscape, true);', self.html)

    def test_ime_composition_guards_are_present(self):
        self.assertIn('msgInput.addEventListener("compositionstart", () => { state.composing = true; });', self.html)
        self.assertIn('msgInput.addEventListener("compositionend",   () => { state.composing = false; });', self.html)


if __name__ == '__main__':
    unittest.main()

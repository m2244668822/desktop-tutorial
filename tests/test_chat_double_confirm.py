import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / "templates" / "chat.html"


class ChatDoubleConfirmTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding="utf-8")

    def test_primary_send_controls_require_double_confirmation(self):
        self.assertIn("function confirmAndSendMessage()", self.html)
        self.assertIn("SEND_CONFIRM_WINDOW_MS", self.html)
        self.assertIn("pendingSend", self.html)
        self.assertIn('onclick="confirmAndSendMessage()"', self.html)
        self.assertNotIn('onclick="sendMessage()"', self.html)
        self.assertIn("function handleMessageKeydown(e)", self.html)
        self.assertIn("confirmAndSendMessage();", self.html)
        self.assertIn('msgInput.addEventListener("keydown", handleMessageKeydown);', self.html)

    def test_no_ui_helper_bypasses_send_confirmation(self):
        direct_calls = re.findall(r"(?<!function )\bsendMessage\(\);", self.html)
        self.assertEqual(
            ["sendMessage();"],
            direct_calls,
            "Only the double-confirm wrapper should call sendMessage() directly.",
        )

    def test_copy_tells_user_send_is_two_step(self):
        self.assertIn("按兩次", self.html)
        self.assertIn("再按一次送出", self.html)

    def test_quick_reply_buttons_submit_immediately(self):
        self.assertIn("function submitQuickReply", self.html)
        self.assertRegex(
            self.html,
            r"btn\.onclick\s*=\s*\(\)\s*=>\s*\{\s*submitQuickReply\(r\)",
        )
        self.assertIn('sendMessage({ source: "quick_reply", force: true })', self.html)


if __name__ == "__main__":
    unittest.main()

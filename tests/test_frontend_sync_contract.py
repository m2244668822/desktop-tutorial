import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / "templates" / "chat.html"


class FrontendSyncContractTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding="utf-8")

    def test_only_trevor_is_a_public_navigation_identity(self):
        self.assertIn('id="nav-trevor"', self.html)
        for legacy in ("engineer", "researcher", "learner", "xiaobian", "whitehat"):
            self.assertNotIn(f'id="nav-{legacy}"', self.html)

    def test_capability_and_deliberation_controls_cover_public_contract(self):
        self.assertIn('id="capabilitySelect"', self.html)
        self.assertIn('id="deliberationSelect"', self.html)
        for mode in ("general", "coding", "research", "security", "content", "learning"):
            self.assertIn(f'<option value="{mode}">', self.html)
        for mode in ("fast", "cross_check", "rigorous"):
            self.assertIn(f'<option value="{mode}">', self.html)
        self.assertIn("capability_mode:", self.html)
        self.assertIn("deliberation:", self.html)

    def test_horde_jobs_poll_without_browser_secret(self):
        self.assertIn("async function runAIHordeJob", self.html)
        self.assertIn('fetch("/api/ai-horde/jobs"', self.html)
        self.assertIn("poll_after_ms", self.html)
        self.assertNotIn("AI_HORDE_API_KEY", self.html)

    def test_message_send_keeps_double_confirmation(self):
        self.assertIn("function handleMessageKeydown", self.html)
        self.assertIn("confirmAndSendMessage();", self.html)
        self.assertIn("function resetSendConfirmation", self.html)


if __name__ == "__main__":
    unittest.main()

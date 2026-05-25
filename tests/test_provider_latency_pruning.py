import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / ".sync_user_project" / "chatgpt_server.py"
CHAT_TEMPLATE_PATH = ROOT / ".sync_user_project" / "templates" / "chat.html"


class ProviderLatencyPruningTests(unittest.TestCase):
    def setUp(self):
        self.server = SERVER_PATH.read_text(encoding="utf-8")
        self.chat = CHAT_TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_backend_disables_slow_cloud_providers_by_default(self):
        self.assertIn(
            'SLOW_PROVIDER_DEFAULTS = {"openrouter", "together", "zhizengzeng"}',
            self.server,
        )
        self.assertIn("DISABLED_CLOUD_PROVIDERS", self.server)
        self.assertIn(
            '"disabled_cloud_providers": model_info.get("disabled_cloud_providers", [])',
            self.server,
        )
        self.assertIn(
            '"provider_catalog": model_info.get("provider_catalog", [])', self.server
        )

    def test_frontend_removes_slow_provider_cards_from_hub(self):
        self.assertNotIn('id="mc-openrouter"', self.chat)
        self.assertNotIn('id="mc-together"', self.chat)
        self.assertNotIn('id="mc-zhizengzeng"', self.chat)
        self.assertIn("已停用", self.chat)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SERVER_PATH = ROOT / "core" / "web_server.py"
CHAT_TEMPLATE_PATH = ROOT / "templates" / "chat.html"
IDENTITY_PATH = ROOT / "core" / "trevor_identity.py"


class ImageGenerationFeatureTests(unittest.TestCase):
    def setUp(self):
        self.server = WEB_SERVER_PATH.read_text(encoding="utf-8")
        self.chat = CHAT_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.identity = IDENTITY_PATH.read_text(encoding="utf-8")

    def test_backend_exposes_ai_horde_as_trevor_capability(self):
        self.assertIn("AIHordeClient", self.server)
        self.assertIn('"/api/ai-horde/jobs"', self.server)
        self.assertIn('"/api/ai-horde/assets/"', self.server)
        self.assertIn("AIHordeJobManager", self.server)
        self.assertNotIn("OPENAI_IMAGE_MODEL", self.server)

    def test_frontend_has_visible_image_generation_controls_and_renderer(self):
        self.assertIn('<option value="image_generation">圖像生成</option>', self.chat)
        self.assertIn('id="imageModeBtn"', self.chat)
        self.assertIn("function runAIHordeJob", self.chat)
        self.assertIn("generated-image-grid", self.chat)
        self.assertNotIn("AI_HORDE_API_KEY", self.chat)

    def test_visual_generation_remains_under_single_trevor_identity(self):
        self.assertIn("TREVOR_AGENT_ID = 'trevor'", self.identity)
        self.assertIn("'content'", self.identity)
        self.assertNotIn("image_generation", self.identity)


if __name__ == "__main__":
    unittest.main()

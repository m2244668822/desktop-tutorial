import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "chatgpt_server.py"
CHAT_TEMPLATE_PATH = ROOT / "templates" / "chat.html"
AGENTS_PATH = ROOT / "agents.py"


class ImageGenerationFeatureTests(unittest.TestCase):
    def setUp(self):
        self.server = SERVER_PATH.read_text(encoding="utf-8")
        self.chat = CHAT_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.agents = AGENTS_PATH.read_text(encoding="utf-8")

    def test_backend_exposes_image_generation_capability(self):
        self.assertIn("OPENAI_IMAGE_MODEL", self.server)
        self.assertIn("def is_image_generation_request", self.server)
        self.assertIn("def generate_agent_image", self.server)
        self.assertIn("images/generations", self.server)
        self.assertIn("local_svg_preview", self.server)
        self.assertIn('"images": generated_images', self.server)
        self.assertIn('"image_generation"', self.server)

    def test_frontend_has_visible_image_generation_controls_and_renderer(self):
        self.assertIn('<option value="image_generation">圖像生成</option>', self.chat)
        self.assertIn('id="imageModeBtn"', self.chat)
        self.assertIn("啟用圖像生成", self.chat)
        self.assertIn("function enableImageGenerationMode()", self.chat)
        self.assertIn("function appendGeneratedImages", self.chat)
        self.assertIn("generated-image-grid", self.chat)
        self.assertIn("image_generation", self.chat)

    def test_agents_advertise_visual_generation(self):
        self.assertIn("image_generation", self.agents)
        self.assertIn("圖片生成", self.agents)
        self.assertIn("視覺生成", self.agents)


if __name__ == "__main__":
    unittest.main()

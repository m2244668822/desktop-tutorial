import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


class FrontendProviderCatalogTests(unittest.TestCase):
    def test_openrouter_with_key_is_visible_and_enabled(self):
        from core.llm_cns import frontend_provider_status

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / ".env").write_text(
                "OPENROUTER_API_KEY=test-openrouter-key\n"
                "OPENROUTER_FREE_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free\n",
                encoding="utf-8",
            )

            status = frontend_provider_status(workspace)
            entry = next(
                item for item in status["provider_catalog"] if item["key"] == "openrouter"
            )

            self.assertEqual("OpenRouter", entry["label"])
            self.assertTrue(entry["visible"])
            self.assertTrue(entry["enabled"])
            self.assertEqual(5, status["total_count"])
            self.assertEqual(1, status["connected_count"])

    def test_openrouter_is_a_valid_explicit_desktop_backend(self):
        from core.llm_cns import frontend_provider_status

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            status = frontend_provider_status(workspace)
            keys = {item["key"] for item in status["provider_catalog"]}

            self.assertIn("openrouter", keys)

    def test_openrouter_uses_process_environment_when_workspace_has_no_env_file(self):
        from core.llm_cns import frontend_provider_status

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                "OPENROUTER_API_KEY": "process-openrouter-key",
                "OPENROUTER_FREE_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free",
            },
            clear=False,
        ):
            status = frontend_provider_status(Path(temp_dir))
            entry = next(
                item for item in status["provider_catalog"] if item["key"] == "openrouter"
            )

            self.assertTrue(entry["enabled"])
            self.assertEqual(1, status["connected_count"])


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT_TEMPLATE_PATH = ROOT / "templates" / "chat.html"


class LearnerResearcherFusionTests(unittest.TestCase):
    def test_legacy_learning_and_research_roles_become_capability_modes(self):
        from core.trevor_identity import normalize_trevor_identity

        learner = normalize_trevor_identity(agent="learner")
        researcher = normalize_trevor_identity(agent="researcher")

        self.assertEqual("trevor", learner.agent)
        self.assertEqual("learning", learner.capability_mode)
        self.assertEqual("trevor", researcher.agent)
        self.assertEqual("research", researcher.capability_mode)
        self.assertTrue(learner.deprecated_alias)
        self.assertTrue(researcher.deprecated_alias)

    def test_frontend_exposes_modes_without_public_legacy_navigation(self):
        chat = CHAT_TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn('id="nav-trevor"', chat)
        self.assertIn('<option value="research">研究</option>', chat)
        self.assertIn('<option value="learning">學習</option>', chat)
        self.assertNotIn('id="nav-learner"', chat)
        self.assertNotIn('id="nav-researcher"', chat)


if __name__ == "__main__":
    unittest.main()

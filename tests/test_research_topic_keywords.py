import unittest


class ResearchTopicKeywordTests(unittest.TestCase):
    def test_research_and_learning_are_capabilities_not_public_agents(self):
        from core.trevor_identity import CAPABILITY_MODES, capability_mode_for_alias

        self.assertEqual(
            ("general", "coding", "research", "security", "content", "learning"),
            CAPABILITY_MODES,
        )
        self.assertEqual("research", capability_mode_for_alias("研究員"))
        self.assertEqual("learning", capability_mode_for_alias("學習器"))


if __name__ == "__main__":
    unittest.main()

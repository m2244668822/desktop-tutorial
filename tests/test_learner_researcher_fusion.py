import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / ".sync_user_project" / "chatgpt_server.py"
AGENTS_PATH = ROOT / ".sync_user_project" / "agents.py"
CHAT_TEMPLATE_PATH = ROOT / ".sync_user_project" / "templates" / "chat.html"
SIDEBAR_PATH = ROOT / "cursor-agent-sidebar-extension" / "media" / "sidebar.js"


def load_agents_module():
    module_name = "agent_specs_under_test"
    spec = importlib.util.spec_from_file_location(module_name, AGENTS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class LearnerResearcherFusionTests(unittest.TestCase):
    def test_researcher_spec_absorbs_learner_capabilities(self):
        agents = load_agents_module()
        researcher = agents.get_agent_spec("researcher")

        self.assertIsNotNone(researcher)
        self.assertEqual(researcher.label, "研究學習中樞")
        self.assertIn("knowledge_distillation", researcher.capabilities)
        self.assertIn("kal_management", researcher.capabilities)
        self.assertIn("方法論", researcher.signal_tags)
        self.assertIn("蒸餾", researcher.signal_tags)
        self.assertNotIn("learner", researcher.collaborators)

    def test_backend_fuses_learner_to_researcher(self):
        source = SERVER_PATH.read_text(encoding="utf-8")

        self.assertIn("FUSE_LEARNER_TO_RESEARCHER", source)
        self.assertIn('normalized == "learner"', source)
        self.assertIn('return "researcher"', source)
        self.assertIn('hidden_keys.add("learner")', source)
        self.assertIn('partner_keys.append("learner")', source)

    def test_frontend_presents_researcher_as_learning_hub(self):
        chat = CHAT_TEMPLATE_PATH.read_text(encoding="utf-8")
        sidebar = SIDEBAR_PATH.read_text(encoding="utf-8")

        self.assertNotIn('id="nav-learner"', chat)
        self.assertIn("研究學習中樞", chat)
        self.assertIn("知識蒸餾", chat)
        self.assertNotIn('"learner",', sidebar)
        self.assertNotIn('learner: "學習器"', sidebar)


if __name__ == "__main__":
    unittest.main()

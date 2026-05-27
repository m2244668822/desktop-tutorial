import ast
import unittest
from pathlib import Path


SERVER_PATH = (
    Path(__file__).resolve().parents[1] / ".sync_user_project" / "chatgpt_server.py"
)


def load_topic_keywords():
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOPIC_KEYWORDS":
                    return ast.literal_eval(node.value)
    raise AssertionError("TOPIC_KEYWORDS was not found")


class ResearchTopicKeywordTests(unittest.TestCase):
    def test_research_topics_include_requested_business_and_support_categories(self):
        topics = load_topic_keywords()

        expected_keywords = {
            "startup": {"創業", "新創", "商業模式"},
            "disability_welfare": {"身心障礙", "身障", "補助"},
            "tenders": {"標案", "招標", "投標"},
            "brainstorming": {"頭腦風暴", "腦力激盪", "發想"},
            "psychiatry": {"精神病學", "精神醫學", "psychiatry"},
            "hematology": {"血液學", "血液科", "hematology"},
            "genetic_diseases": {"遺傳病學", "遺傳疾病", "genetic disease"},
            "linguistics": {"語言學", "語用學", "linguistics"},
            "methodology": {"方法論", "研究方法", "methodology"},
            "distillation": {"蒸餾法", "知識蒸餾", "distillation"},
            "philosophical_suicide_logic": {
                "哲學自殺邏輯",
                "哲學自殺",
                "自殺邏輯",
            },
        }

        for topic, keywords in expected_keywords.items():
            self.assertIn(topic, topics)
            self.assertTrue(keywords.issubset(set(topics[topic])))


if __name__ == "__main__":
    unittest.main()

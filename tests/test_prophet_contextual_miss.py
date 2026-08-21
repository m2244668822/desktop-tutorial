import unittest

from core.langgraph_workflow import _format_prophet_result


class ProphetContextualMissTests(unittest.TestCase):
    def test_contextual_miss_uses_memory_without_unrelated_elijah_hint(self):
        result = _format_prophet_result(
            {
                "knowledge_hub": {"exists": True},
                "long_term_memory": {
                    "matches": [
                        {
                            "source": "agent_memory_assistant",
                            "timestamp": "2026-05-20T10:49:31",
                            "summary": "固定模板回覆比例太高，造成需求分流與對話品質下降。",
                            "semantic_score": 0.0,
                            "lexical_score": 0.0,
                            "combined_score": 0.22,
                        }
                    ]
                },
                "workspace_search": {"matches": []},
                "catalog": {"matches": []},
            },
            user_input="分析智能體對話鬼打牆沒辦法精準抓到我的需求服務的問題",
        )

        self.assertIn("目前沒有高信心直接命中", result)
        self.assertIn("信心等級：低信心", result)
        self.assertIn("弱關聯來源", result)
        self.assertIn("弱關聯記憶片段", result)
        self.assertIn("需求分流", result)
        self.assertIn("前後文", result)
        self.assertIn("下一個應問的具體缺口", result)
        self.assertNotIn("Elijah", result)
        self.assertNotIn("聖經資料索引", result)

    def test_high_score_memory_without_topic_overlap_is_not_direct_hit(self):
        result = _format_prophet_result(
            {
                "knowledge_hub": {"exists": True},
                "long_term_memory": {
                    "matches": [
                        {
                            "source": "agent_memory_assistant",
                            "timestamp": "2026-02-25T10:45:00",
                            "summary": "自然語言處理是人工智能的一個領域，應用包括文本分類與機器翻譯。",
                            "semantic_score": 0.42,
                            "lexical_score": 0.0,
                            "combined_score": 0.42,
                        }
                    ]
                },
                "workspace_search": {"matches": []},
                "catalog": {"matches": []},
            },
            user_input="為什麼系統主動巡查快照顯示 Git 狀態為受限，OpenClaw forwarding 卡在哪裡？",
        )

        self.assertIn("信心等級：低信心", result)
        self.assertIn("弱關聯來源", result)
        self.assertNotIn("長期記憶高信心命中", result)
        self.assertNotIn("自然語言處理是人工智能", result)


if __name__ == "__main__":
    unittest.main()

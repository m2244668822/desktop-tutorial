import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory_layers import ThreeLayerMemory, collect_memory_sources
from core.workflow_runtime import _tool_aeg_keyword_graph


def _write_chatgpt_db(root: Path) -> None:
    db_path = root / "500" / "llama32-chat" / "data" / "local_knowledge" / "complete_chatgpt_database.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "conversations": [
                {
                    "id": "conv-low-confidence",
                    "title": "LangGraph 低信心與鬼打牆修復",
                    "create_time": 1780000000,
                    "mapping": {
                        "m1": {
                            "message": {
                                "author": {"role": "user"},
                                "content": {"parts": ["智能體鬼打牆，未找到直接命中，應分析前後文與弱關聯。"]},
                            }
                        },
                        "m2": {
                            "message": {
                                "author": {"role": "assistant"},
                                "content": {"parts": ["需要輸出信心等級、弱關聯來源、建議關鍵詞、下一個缺口。"]},
                            }
                        },
                    },
                }
            ]
        }
    }
    db_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class AegChatGptTrainingSourceTests(unittest.TestCase):
    def test_collect_memory_sources_includes_full_chatgpt_database_and_rebuilds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_chatgpt_db(root)

            sources = collect_memory_sources(root)
            source_names = {item["source"] for item in sources}
            self.assertIn("chatgpt_database_user", source_names)
            self.assertIn("chatgpt_database_assistant", source_names)

            memory = ThreeLayerMemory(root)
            result = memory.rebuild(sources)
            self.assertGreaterEqual(result["items_indexed"], 2)
            self.assertGreaterEqual(result["dedupe"]["deduped_items"], 2)
            stats = memory.stats()
            self.assertIn("faiss_available", stats)
            self.assertIn("faiss_file_exists", stats)

            matches = memory.search("鬼打牆 弱關聯", top_k=3)
            self.assertTrue(matches)
            self.assertTrue(any(match["source"].startswith("chatgpt_database") for match in matches))

    def test_aeg_keyword_graph_tracks_chatgpt_database_source_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_chatgpt_db(root)

            result = _tool_aeg_keyword_graph(root, {"limit": 30})
            self.assertGreaterEqual(result["text_items"], 2)
            self.assertGreaterEqual(result["source_breakdown"].get("chatgpt_database", 0), 2)
            self.assertGreater(result["readable_ratio"], 0)


if __name__ == "__main__":
    unittest.main()

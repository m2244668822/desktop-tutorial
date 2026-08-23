import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.agent_memory_manager import AgentMemoryManager


class AgentMemoryAutosaveNoiseTests(unittest.TestCase):
    def test_autosave_skips_when_memory_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = AgentMemoryManager(base_dir=tmp, auto_save=False)
            manager._last_save_time = datetime.now() - timedelta(seconds=31)

            self.assertFalse(manager._should_save())
            status = manager.get_save_status()
            self.assertFalse(status["dirty"])
            self.assertGreaterEqual(status["skipped_since_start"], 1)
            self.assertFalse(status["auto_save_enabled"])

    def test_mutation_marks_dirty_and_successful_save_clears_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = AgentMemoryManager(base_dir=tmp, auto_save=False)

            manager.save_conversation("總管", "測試訊息", "測試回覆")
            status = manager.get_save_status()
            self.assertTrue(status["dirty"])
            self.assertGreaterEqual(status["dirty_reasons"].get("conversations", 0), 1)

            manager._save_all(reason="unit_test")
            status = manager.get_save_status()
            self.assertFalse(status["dirty"])
            self.assertGreaterEqual(status["save_success_since_start"], 1)
            self.assertTrue(Path(tmp, "data", "agent_memories", "conversations.json").exists())


if __name__ == "__main__":
    unittest.main()

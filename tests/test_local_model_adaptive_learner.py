from __future__ import annotations

import sys
from pathlib import Path


LEARNING_DIR = Path(__file__).resolve().parents[1] / "500" / "llama32-chat" / "learning"
if str(LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(LEARNING_DIR))

from local_model_adaptive_learner import LocalModelAdaptivelearner


def test_monitor_performance_uses_total_items_learned(tmp_path: Path) -> None:
    learner = LocalModelAdaptivelearner(
        training_data_file=str(tmp_path / "training.json"),
        model_state_file=str(tmp_path / "model_state.json"),
        performance_log_file=str(tmp_path / "performance.json"),
    )
    learner.learned_knowledge["recommended_approach"] = [
        {"data": {"confidence": 0.95}} for _ in range(101)
    ]

    result = learner.monitor_performance()

    assert result["learning_progress"]["total_items_learned"] == 101
    assert result["recommendations"][0]["action"] == "consolidate_learning"

import json
import tempfile
from pathlib import Path


def test_migrated_chatgpt_history_counts_as_ready_without_legacy_raw_file():
    from core.data_paths import ProjectPaths
    from core.knowledge_hub import _chatgpt_source_status

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        paths = ProjectPaths(root)
        manifest = paths.data / "migrations" / "trevor_data_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps(
                {
                    "identity": "trevor",
                    "rerunnable": True,
                    "source_counts": {"chatgpt_database": 12},
                }
            ),
            encoding="utf-8",
        )

        status = _chatgpt_source_status(paths)

        assert status["chatgpt_database_ready"] is True
        assert status["raw_chatgpt_database_ready"] is False
        assert status["migrated_chatgpt_database_ready"] is True
        assert status["migrated_chatgpt_turns"] == 12


def test_empty_or_invalid_migration_does_not_claim_chatgpt_ready():
    from core.data_paths import ProjectPaths
    from core.knowledge_hub import _chatgpt_source_status

    with tempfile.TemporaryDirectory() as td:
        paths = ProjectPaths(Path(td))
        status = _chatgpt_source_status(paths)
        assert status["chatgpt_database_ready"] is False
        assert status["migrated_chatgpt_database_ready"] is False

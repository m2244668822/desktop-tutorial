import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class KnowledgeIngestionDedupTests(unittest.TestCase):
    def test_pipeline_uses_configured_trevor_data_directory(self):
        from tools.build_knowledge_ingestion import build_pipeline

        with tempfile.TemporaryDirectory() as workspace_tmp, tempfile.TemporaryDirectory() as data_tmp:
            workspace = Path(workspace_tmp)
            data_root = Path(data_tmp)
            (workspace / "docs").mkdir()
            (workspace / "docs" / "one.md").write_text(
                "這是一份足夠長度的有效知識文件。",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"TREVOR_DATA_DIR": str(data_root)}):
                summary = build_pipeline(workspace)

            self.assertEqual(str(data_root.resolve()), summary["data_root"])
            self.assertTrue(
                (data_root / "knowledge_hub" / "ingestion" / "summary.json").exists()
            )
            self.assertFalse((workspace / "data").exists())

    def test_identical_content_keeps_first_source_and_records_duplicate(self):
        from tools.build_knowledge_ingestion import (
            IngestedDocument,
            _dedupe_documents_by_content,
        )

        first = IngestedDocument(
            doc_id="first",
            source="docs",
            path="canonical.md",
            title="canonical",
            text="同一份內容，保留第一個來源。",
            metadata={},
        )
        duplicate = IngestedDocument(
            doc_id="second",
            source="reports",
            path="snapshot.md",
            title="snapshot",
            text="同一份內容，保留第一個來源。",
            metadata={},
        )

        kept, duplicates = _dedupe_documents_by_content([first, duplicate])

        self.assertEqual([first], kept)
        self.assertEqual(1, len(duplicates))
        self.assertEqual("canonical.md", duplicates[0]["kept_path"])
        self.assertEqual("snapshot.md", duplicates[0]["skipped_path"])

    def test_formatting_only_differences_are_deduplicated(self):
        from tools.build_knowledge_ingestion import (
            IngestedDocument,
            _dedupe_documents_by_content,
        )

        documents = [
            IngestedDocument("a", "docs", "a.md", "a", "alpha\n beta", {}),
            IngestedDocument("b", "docs", "b.md", "b", " alpha   beta ", {}),
            IngestedDocument("c", "docs", "c.md", "c", "different", {}),
        ]

        kept, duplicates = _dedupe_documents_by_content(documents)

        self.assertEqual(["a", "c"], [document.doc_id for document in kept])
        self.assertEqual(1, len(duplicates))


if __name__ == "__main__":
    unittest.main()

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path


class MigrationStatusExportTests(unittest.TestCase):
    def test_export_keeps_status_and_removes_device_private_data(self):
        from core.migration_status import export_public_migration_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "public"
            source.mkdir()
            (source / "trevor_data_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "identity": "trevor",
                        "generated_at": "2026-08-25T00:00:00+00:00",
                        "unique_turns": 5426,
                        "conversation_threads": 1385,
                        "copied_files": ["/Users/private/secret.json"],
                        "source_counts": {"private_chat": 5426},
                        "deduplication": "sha256_normalized_turn",
                        "rerunnable": True,
                    }
                ),
                encoding="utf-8",
            )
            (source / "graphiti_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "graphiti_version": "0.29.3",
                        "identity": "trevor",
                        "generated_at": "2026-08-25T01:00:00+00:00",
                        "migrated_count": 5426,
                        "source_count": 5426,
                        "failed_count": 0,
                        "completed": True,
                        "status": "completed",
                        "content_hashes": ["a" * 64],
                        "deduplication": "sha256_normalized_turn",
                        "redacted_before_upload": True,
                        "rerunnable": True,
                        "batching": {"batch_count": 314},
                    }
                ),
                encoding="utf-8",
            )

            result = export_public_migration_status(source, destination)

            self.assertEqual(5426, result["graphiti"]["migrated_count"])
            self.assertEqual(5426, result["device"]["unique_turns"])
            device = json.loads(
                (destination / "trevor_data_manifest.json").read_text(encoding="utf-8")
            )
            graphiti = json.loads(
                (destination / "graphiti_manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("copied_files", device)
            self.assertNotIn("source_counts", device)
            self.assertNotIn("content_hashes", graphiti)
            self.assertTrue(device["encrypted"])
            self.assertTrue(graphiti["redacted_before_upload"])
            self.assertEqual(
                stat.S_IMODE(os.stat(destination / "graphiti_manifest.json").st_mode),
                0o600,
            )

    def test_export_rejects_incomplete_graphiti_migration(self):
        from core.migration_status import export_public_migration_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "trevor_data_manifest.json").write_text(
                json.dumps({"unique_turns": 1, "conversation_threads": 1}),
                encoding="utf-8",
            )
            (source / "graphiti_manifest.json").write_text(
                json.dumps(
                    {
                        "completed": False,
                        "migrated_count": 0,
                        "source_count": 1,
                        "failed_count": 1,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "graphiti_migration_incomplete"):
                export_public_migration_status(source, root / "public")


if __name__ == "__main__":
    unittest.main()

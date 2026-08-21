import json
import tempfile
import unittest
from pathlib import Path


class TrevorDataMigrationTests(unittest.TestCase):
    def test_platform_defaults_and_override(self):
        from core.data_paths import default_trevor_data_dir, resolve_data_root

        self.assertEqual(
            Path('/Users/test/Library/Application Support/Trevor'),
            default_trevor_data_dir(platform_name='Darwin', home=Path('/Users/test')),
        )
        self.assertEqual(
            Path('/var/lib/trevor'),
            default_trevor_data_dir(deployment='oci', platform_name='Linux'),
        )
        self.assertEqual(
            Path('/secure/trevor'),
            resolve_data_root('/workspace', env={'TREVOR_DATA_DIR': '/secure/trevor'}),
        )

    def test_migration_is_repeatable_deduplicated_and_preserves_source_role(self):
        from core.data_migration import TrevorDataMigrator

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            destination = Path(tmp) / 'runtime'
            memory_dir = workspace / 'data' / 'agent_memories'
            legacy_dir = workspace / '500' / 'llama32-chat' / 'data'
            memory_dir.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)
            (memory_dir / 'conversations.json').write_text(
                json.dumps(
                    {
                        'legacy-thread': {
                            'agent_name': '工程師',
                            'created_at': '2026-01-01',
                            'last_message_at': '2026-01-01',
                            'messages': [
                                {
                                    'timestamp': '2026-01-01',
                                    'user': '重複問題',
                                    'assistant': '重複答案',
                                    'metadata': {},
                                }
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )
            (legacy_dir / 'conversations.json').write_text(
                json.dumps(
                    [
                        {'prompt': '重複問題', 'response': '重複答案', 'timestamp': '2026-01-01'},
                        {'prompt': '新問題', 'response': '新答案', 'timestamp': '2026-01-02'},
                    ],
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )

            migrator = TrevorDataMigrator(workspace, destination)
            first = migrator.migrate()
            second = migrator.migrate()
            conversations = json.loads(
                (destination / 'agent_memories' / 'conversations.json').read_text(encoding='utf-8')
            )
            manifest_exists = (
                destination / 'migrations' / 'trevor_data_manifest.json'
            ).exists()

        messages = [message for thread in conversations.values() for message in thread['messages']]
        self.assertEqual(2, len(messages))
        self.assertEqual(2, first['unique_turns'])
        self.assertEqual(first['unique_turns'], second['unique_turns'])
        self.assertEqual({'崔佛'}, {thread['agent_name'] for thread in conversations.values()})
        self.assertIn('工程師', {message['metadata']['source_role'] for message in messages})
        self.assertTrue(manifest_exists)


if __name__ == '__main__':
    unittest.main()

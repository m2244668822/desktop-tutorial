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
        from core.encrypted_store import AESGCMJsonStore

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

            store = AESGCMJsonStore(lambda: b'd' * 32)
            migrator = TrevorDataMigrator(workspace, destination, json_store=store)
            first = migrator.migrate()
            second = migrator.migrate()
            destination_file = destination / 'agent_memories' / 'conversations.json'
            conversations = store.read_json(destination_file, {})
            raw_destination = destination_file.read_text(encoding='utf-8')
            destination_is_encrypted = store.is_encrypted(destination_file)
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
        self.assertNotIn('重複問題', raw_destination)
        self.assertTrue(destination_is_encrypted)

    def test_complete_chatgpt_database_is_grouped_and_encrypted(self):
        from core.data_migration import TrevorDataMigrator
        from core.encrypted_store import AESGCMJsonStore

        def message_node(node_id, parent, role, text, timestamp):
            return {
                'id': node_id,
                'parent': parent,
                'children': [],
                'message': {
                    'id': f'message-{node_id}',
                    'author': {'role': role, 'name': None, 'metadata': {}},
                    'content': {'content_type': 'text', 'parts': [text]},
                    'create_time': timestamp,
                    'metadata': {'model_slug': 'test-model'},
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            destination = Path(tmp) / 'runtime'
            database = (
                workspace
                / '500'
                / 'llama32-chat'
                / 'data'
                / 'local_knowledge'
                / 'complete_chatgpt_database.json'
            )
            database.parent.mkdir(parents=True)
            database.write_text(
                json.dumps(
                    {
                        'data': {
                            'conversations': [
                                {
                                    'id': 'conversation-one',
                                    'current_node': 'a2',
                                    'create_time': 1_700_000_000,
                                    'mapping': {
                                        'u1': message_node('u1', None, 'user', '第一問', 1_700_000_001),
                                        'a1': message_node('a1', 'u1', 'assistant', '第一答', 1_700_000_002),
                                        'u2': message_node('u2', 'a1', 'user', '第二問', 1_700_000_003),
                                        'a2': message_node('a2', 'u2', 'assistant', '第二答', 1_700_000_004),
                                    },
                                },
                                {
                                    'id': 'conversation-two',
                                    'current_node': 'b1',
                                    'create_time': 1_700_000_010,
                                    'mapping': {
                                        'u1': message_node('u1', None, 'user', '第三問', 1_700_000_011),
                                        'b1': message_node('b1', 'u1', 'assistant', '第三答', 1_700_000_012),
                                    },
                                },
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )
            store = AESGCMJsonStore(lambda: b'e' * 32)

            result = TrevorDataMigrator(
                workspace, destination, json_store=store
            ).migrate()
            destination_file = destination / 'agent_memories' / 'conversations.json'
            conversations = store.read_json(destination_file, {})
            raw_destination = destination_file.read_text(encoding='utf-8')

        self.assertEqual(3, result['unique_turns'])
        self.assertEqual(2, result['conversation_threads'])
        self.assertEqual(3, result['source_counts']['chatgpt_database'])
        self.assertEqual([2, 1], sorted(
            (len(thread['messages']) for thread in conversations.values()),
            reverse=True,
        ))
        self.assertNotIn('第一問', raw_destination)


if __name__ == '__main__':
    unittest.main()

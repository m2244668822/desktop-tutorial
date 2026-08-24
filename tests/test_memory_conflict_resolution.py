import json
import tempfile
import unittest
from pathlib import Path


class MemoryConflictResolutionTests(unittest.TestCase):
    def test_explicit_user_preference_beats_model_inference(self):
        from core.memory_conflicts import MemoryConflictResolver

        resolver = MemoryConflictResolver()
        existing = {
            'key': 'response.style',
            'value': 'concise',
            'source': 'user_explicit',
            'updated_at': '2026-01-01T00:00:00+00:00',
        }
        incoming = {
            'key': 'response.style',
            'value': 'verbose',
            'source': 'model_inferred',
            'updated_at': '2026-08-21T00:00:00+00:00',
        }

        decision = resolver.resolve(existing, incoming)

        self.assertEqual('concise', decision.winner['value'])
        self.assertTrue(decision.conflict)
        self.assertEqual('source_precedence', decision.reason)

    def test_restrictive_safety_rule_cannot_be_weakened(self):
        from core.memory_conflicts import MemoryConflictResolver

        resolver = MemoryConflictResolver()
        deny = {
            'key': 'permission.destructive_delete',
            'value': 'deny',
            'source': 'system_policy',
        }
        allow = {
            'key': 'permission.destructive_delete',
            'value': 'allow',
            'source': 'user_explicit',
            'priority': 999,
        }

        decision = resolver.resolve(deny, allow)

        self.assertEqual('deny', decision.winner['value'])
        self.assertEqual('safety_deny_wins', decision.reason)

    def test_legacy_roles_write_one_trevor_conversation_without_duplicates(self):
        from tools.agent_memory_manager import AgentMemoryManager

        with tempfile.TemporaryDirectory() as tmp:
            manager = AgentMemoryManager(tmp, auto_save=False)
            manager.save_conversation('工程師', '同一問題', '同一答案')
            manager.save_conversation('研究員', '同一問題', '同一答案')
            history = manager.get_conversation_history('崔佛', limit=20)

        self.assertEqual(1, len(history))
        self.assertEqual('崔佛', history[0]['agent_name'])
        self.assertEqual(1, len(history[0]['messages']))
        metadata = history[0]['messages'][0]['metadata']
        self.assertEqual('工程師', metadata['source_role'])
        self.assertEqual('coding', metadata['capability_mode'])

    def test_loaded_legacy_memory_is_normalized_once(self):
        from tools.agent_memory_manager import AgentMemoryManager

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / 'data' / 'agent_memories'
            memory_dir.mkdir(parents=True)
            (memory_dir / 'agent_memories.json').write_text(
                json.dumps(
                    {
                        '工程師': {
                            'last_updated': '2026-01-01T00:00:00+00:00',
                            'memories': [{'timestamp': '2026-01-01', 'data': {'fact': 'A'}}],
                            'preferences': {'tone': 'precise'},
                        },
                        '小編': {
                            'last_updated': '2026-02-01T00:00:00+00:00',
                            'memories': [{'timestamp': '2026-02-01', 'data': {'fact': 'B'}}],
                            'preferences': {'tone': 'friendly'},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )
            manager = AgentMemoryManager(tmp, auto_save=False)

        self.assertEqual({'崔佛'}, set(manager._agent_memories))
        self.assertEqual(2, len(manager._agent_memories['崔佛']['memories']))
        self.assertEqual('friendly', manager._agent_memories['崔佛']['preferences']['tone'])
        self.assertTrue(manager._agent_memories['崔佛']['conflicts'])

    def test_save_merges_external_conversation_migration_before_writing(self):
        from core.encrypted_store import AESGCMJsonStore
        from tools.agent_memory_manager import AgentMemoryManager

        with tempfile.TemporaryDirectory() as tmp:
            store = AESGCMJsonStore(lambda: b'm' * 32)
            manager = AgentMemoryManager(
                tmp,
                auto_save=False,
                json_store=store,
            )
            manager.save_conversation('崔佛', '執行中新增', '本機回答')
            external = {
                'imported-thread': {
                    'agent_name': '崔佛',
                    'created_at': '2026-08-24T00:00:00+00:00',
                    'last_message_at': '2026-08-24T00:00:00+00:00',
                    'messages': [
                        {
                            'timestamp': '2026-08-24T00:00:00+00:00',
                            'user': '外部遷移內容',
                            'assistant': '匯入回答',
                            'metadata': {'source': 'chatgpt_database'},
                        }
                    ],
                }
            }
            store.write_json(manager.conversation_file, external)

            manager._save_all(reason='test_external_merge')

            saved = store.read_json(manager.conversation_file, {})

        messages = [
            message
            for thread in saved.values()
            for message in thread.get('messages', [])
        ]
        self.assertEqual(2, len(messages))
        self.assertEqual(
            {'外部遷移內容', '執行中新增'},
            {message['user'] for message in messages},
        )


if __name__ == '__main__':
    unittest.main()

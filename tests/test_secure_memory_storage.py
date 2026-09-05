import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class _MemoryBackend:
    def __init__(self):
        self.values = {}

    def get(self, service, account):
        return self.values.get((service, account))

    def set(self, service, account, value):
        self.values[(service, account)] = value

    def delete(self, service, account):
        self.values.pop((service, account), None)


class SecureMemoryStorageTests(unittest.TestCase):
    def test_credential_result_repr_never_leaks_secret(self):
        from core.keychain_credentials import KeychainCredentialStore

        backend = _MemoryBackend()
        backend.set('trevor.test', 'api-key', 'super-secret-value')
        result = KeychainCredentialStore(backend=backend).get_secret('trevor.test', 'api-key')

        self.assertTrue(result.configured)
        self.assertEqual('super-secret-value', result.value)
        self.assertNotIn('super-secret-value', repr(result))
        self.assertEqual({'configured': True, 'source': 'keychain'}, result.public_status())

    def test_aes_gcm_round_trip_has_no_plaintext_and_detects_tampering(self):
        from core.encrypted_store import AESGCMJsonStore, EncryptedStoreError

        key = bytes(range(32))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'memory.json'
            store = AESGCMJsonStore(lambda: key)
            store.write_json(path, {'private_note': '不能出現在磁碟'})
            raw = path.read_text(encoding='utf-8')
            loaded = store.read_json(path, {})
            envelope = json.loads(raw)
            envelope['ciphertext'] = envelope['ciphertext'][:-2] + 'AA'
            path.write_text(json.dumps(envelope), encoding='utf-8')

            with self.assertRaises(EncryptedStoreError):
                store.read_json(path, {})

        self.assertNotIn('不能出現在磁碟', raw)
        self.assertEqual({'private_note': '不能出現在磁碟'}, loaded)
        self.assertEqual('AES-256-GCM', json.loads(raw)['algorithm'])

    def test_plain_json_can_be_read_then_rewritten_encrypted(self):
        from core.encrypted_store import AESGCMJsonStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'legacy.json'
            path.write_text('{"legacy": true}', encoding='utf-8')
            store = AESGCMJsonStore(lambda: b'k' * 32)

            self.assertEqual({'legacy': True}, store.read_json(path, {}))
            self.assertFalse(store.is_encrypted(path))
            store.reencrypt_json(path)
            self.assertTrue(store.is_encrypted(path))
            self.assertEqual({'legacy': True}, store.read_json(path, {}))

    def test_in_memory_json_envelope_round_trip(self):
        from core.encrypted_store import AESGCMJsonStore

        store = AESGCMJsonStore(lambda: b'e' * 32)
        envelope = store.seal_json({'private': '不落地的內容'})

        self.assertEqual('AES-256-GCM', envelope['algorithm'])
        self.assertNotIn('不落地的內容', json.dumps(envelope, ensure_ascii=False))
        self.assertEqual({'private': '不落地的內容'}, store.open_json(envelope))

    def test_memory_index_encrypts_private_fields_and_remains_searchable(self):
        from core.encrypted_store import AESGCMJsonStore
        from core.memory_layers import ThreeLayerMemory

        with tempfile.TemporaryDirectory() as tmp:
            store = AESGCMJsonStore(lambda: b'i' * 32)
            memory = ThreeLayerMemory(tmp, json_store=store)
            memory.rebuild(
                [
                    {
                        'source': 'agent_memory_user',
                        'source_id': 'private:1',
                        'role': 'user',
                        'content': '這是不可出現在索引明文中的私人內容',
                        'summary': '私人內容摘要',
                        'timestamp': '',
                        'metadata': {'private_label': '敏感標籤'},
                    }
                ]
            )

            conn = sqlite3.connect(memory.paths.sqlite_path)
            try:
                raw = '\n'.join(str(value) for value in conn.execute(
                    'SELECT content, summary, metadata_json FROM long_term_memory'
                ).fetchone())
            finally:
                conn.close()
            meta_raw = memory.paths.meta_path.read_text(encoding='utf-8')

            self.assertNotIn('私人內容', raw)
            self.assertNotIn('敏感標籤', raw)
            self.assertNotIn('私人內容摘要', meta_raw)
            self.assertTrue(memory.stats()['content_encrypted'])
            self.assertEqual(
                '這是不可出現在索引明文中的私人內容',
                memory.search('私人內容', top_k=1)[0]['content'],
            )

    def test_collect_memory_sources_decrypts_agent_conversations(self):
        from core.encrypted_store import AESGCMJsonStore
        from core.memory_layers import collect_memory_sources

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / 'data'
            path = data_root / 'agent_memories' / 'conversations.json'
            store = AESGCMJsonStore(lambda: b'c' * 32)
            store.write_json(
                path,
                {
                    'thread-1': {
                        'agent_name': '崔佛',
                        'messages': [
                            {
                                'timestamp': '2026-09-05T00:00:00',
                                'user': '使用者的加密問題',
                                'assistant': '崔佛的加密回答依然可以搜尋',
                            }
                        ],
                    }
                },
            )

            sources = collect_memory_sources(root, json_store=store)

            self.assertEqual(
                {'agent_memory_user', 'agent_memory_assistant'},
                {item['source'] for item in sources},
            )

    def test_memory_manager_migrates_and_encrypts_all_private_state(self):
        from core.encrypted_store import AESGCMJsonStore
        from tools.agent_memory_manager import AgentMemoryManager

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / 'data' / 'agent_memories'
            memory_dir.mkdir(parents=True)
            agent_file = memory_dir / 'agent_memories.json'
            agent_file.write_text(
                json.dumps({'工程師': {'memories': [], 'preferences': {}}}, ensure_ascii=False),
                encoding='utf-8',
            )
            store = AESGCMJsonStore(lambda: b'm' * 32)

            manager = AgentMemoryManager(tmp, auto_save=False, json_store=store)
            manager.save_conversation('工程師', '私人問題', '私人答案')
            manager.save_ide_context({'workspace': '私人工作區'})
            manager.start_session('工程師', {'note': '私人會話'})
            manager._save_all(reason='unit_test')

            private_files = (
                manager.agent_memory_file,
                manager.conversation_file,
                manager.ide_context_file,
                manager.session_file,
            )
            self.assertTrue(all(store.is_encrypted(path) for path in private_files))
            self.assertNotIn('私人問題', manager.conversation_file.read_text(encoding='utf-8'))
            self.assertEqual({'崔佛'}, set(store.read_json(agent_file, {})))

    def test_memory_manager_rejects_tampered_encrypted_state(self):
        from core.encrypted_store import AESGCMJsonStore, EncryptedStoreError
        from tools.agent_memory_manager import AgentMemoryManager

        with tempfile.TemporaryDirectory() as tmp:
            memory_dir = Path(tmp) / 'data' / 'agent_memories'
            memory_dir.mkdir(parents=True)
            agent_file = memory_dir / 'agent_memories.json'
            store = AESGCMJsonStore(lambda: b't' * 32)
            store.write_json(agent_file, {'崔佛': {'memories': [], 'preferences': {}}})
            envelope = json.loads(agent_file.read_text(encoding='utf-8'))
            envelope['ciphertext'] = envelope['ciphertext'][:-2] + 'AA'
            agent_file.write_text(json.dumps(envelope), encoding='utf-8')

            with self.assertRaises(EncryptedStoreError):
                AgentMemoryManager(tmp, auto_save=False, json_store=store)


if __name__ == '__main__':
    unittest.main()

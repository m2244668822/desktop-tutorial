import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


class GraphitiMigrationTests(unittest.TestCase):
    def test_cli_can_start_outside_the_repository_working_directory(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'tools' / 'migrate_graphiti.py'), '--help'],
            cwd=Path(tempfile.gettempdir()),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('--base-url', result.stdout)

    def test_rerun_deduplicates_redacts_and_preserves_source_role(self):
        from core.audit_chain import HashChainAuditLog
        from core.graphiti_migration import GraphitiMigrationRunner

        sent = []
        conversations = {
            'thread': {
                'agent_name': '崔佛',
                'messages': [
                    {
                        'timestamp': '2026-08-21T00:00:00+00:00',
                        'user': '我的信箱是 user@example.com',
                        'assistant': '已記住',
                        'metadata': {
                            'source_role': '工程師',
                            'capability_mode': 'coding',
                        },
                    },
                    {
                        'timestamp': '2026-08-21T00:00:00+00:00',
                        'user': '我的信箱是 user@example.com',
                        'assistant': '已記住',
                        'metadata': {'source_role': '研究員'},
                    },
                ],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'graphiti_manifest.json'
            audit = HashChainAuditLog(Path(tmp) / 'audit.jsonl')
            runner = GraphitiMigrationRunner(
                manifest,
                sender=lambda payload: sent.append(payload),
                audit_log=audit,
            )

            first = runner.run(conversations)
            second = runner.run(conversations)
            stored = json.loads(manifest.read_text(encoding='utf-8'))
            audit_events = audit.read()

        self.assertEqual(1, first['migrated'])
        self.assertEqual(0, second['migrated'])
        self.assertEqual(1, len(sent))
        self.assertNotIn('user@example.com', json.dumps(sent, ensure_ascii=False))
        self.assertIn('[REDACTED_EMAIL]', sent[0]['episode_body'])
        self.assertEqual('工程師', sent[0]['metadata']['source_role'])
        self.assertEqual(1, stored['migrated_count'])
        self.assertTrue(stored['completed'])
        self.assertEqual('completed', stored['status'])
        self.assertEqual(1, stored['source_count'])
        self.assertNotIn('episode_body', json.dumps(stored))
        self.assertEqual('data_migration_completed', audit_events[-1]['event_type'])
        self.assertNotIn('user@example.com', json.dumps(audit_events, ensure_ascii=False))

    def test_failed_upload_writes_resumable_incomplete_manifest(self):
        from core.graphiti_migration import GraphitiMigrationRunner

        conversations = {
            'thread': {
                'messages': [
                    {
                        'timestamp': '2026-08-21T00:00:00+00:00',
                        'user': 'hello',
                        'assistant': 'world',
                    }
                ]
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'graphiti_manifest.json'
            runner = GraphitiMigrationRunner(
                manifest,
                sender=lambda _payload: (_ for _ in ()).throw(RuntimeError('offline')),
            )

            result = runner.run(conversations)
            stored = json.loads(manifest.read_text(encoding='utf-8'))

        self.assertFalse(result['ok'])
        self.assertFalse(stored['completed'])
        self.assertEqual('incomplete', stored['status'])
        self.assertEqual(1, stored['source_count'])
        self.assertEqual(1, stored['failed_count'])

    def test_cli_rejects_partial_unified_memory_source(self):
        from tools.migrate_graphiti import load_unified_conversations

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            migration_root = data_root / 'migrations'
            migration_root.mkdir()
            (migration_root / 'trevor_data_manifest.json').write_text(
                json.dumps({'unique_turns': 2}),
                encoding='utf-8',
            )
            manager = SimpleNamespace(
                memory_dir=data_root / 'agent_memories',
                _conversations={
                    'thread': {
                        'messages': [
                            {'user': 'only', 'assistant': 'one', 'metadata': {}}
                        ]
                    }
                },
            )

            with self.assertRaisesRegex(RuntimeError, 'unified_memory_incomplete'):
                load_unified_conversations(manager)

    def test_successful_episode_is_checkpointed_before_interruption(self):
        from core.graphiti_migration import GraphitiMigrationRunner

        conversations = {
            'thread': {
                'messages': [
                    {'user': 'first', 'assistant': 'done'},
                    {'user': 'second', 'assistant': 'pending'},
                ]
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'graphiti_manifest.json'
            calls = []

            def interrupted_sender(payload):
                calls.append(payload['name'])
                if len(calls) == 2:
                    raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                GraphitiMigrationRunner(
                    manifest,
                    sender=interrupted_sender,
                ).run(conversations)

            checkpoint = manifest.with_suffix('.json.checkpoint')
            self.assertTrue(checkpoint.exists())

            resumed = []
            result = GraphitiMigrationRunner(
                manifest,
                sender=lambda payload: resumed.append(payload['name']),
            ).run(conversations)
            checkpoint_removed = not checkpoint.exists()

        self.assertEqual(1, result['migrated'])
        self.assertEqual(1, result['skipped'])
        self.assertEqual(1, len(resumed))
        self.assertTrue(checkpoint_removed)


if __name__ == '__main__':
    unittest.main()

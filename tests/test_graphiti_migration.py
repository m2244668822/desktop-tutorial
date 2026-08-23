import json
import tempfile
import unittest
from pathlib import Path


class GraphitiMigrationTests(unittest.TestCase):
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
        self.assertNotIn('episode_body', json.dumps(stored))
        self.assertEqual('data_migration_completed', audit_events[-1]['event_type'])
        self.assertNotIn('user@example.com', json.dumps(audit_events, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()

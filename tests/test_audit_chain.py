import json
import tempfile
import unittest
from pathlib import Path


class AuditChainTests(unittest.TestCase):
    def test_append_redacts_and_links_events(self):
        from core.audit_chain import HashChainAuditLog

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            audit = HashChainAuditLog(path)
            first = audit.append(
                'provider_switch',
                {'detail': 'GEMINI_API_KEY=private-value owner@example.com'},
            )
            second = audit.append('git_merge', {'branch': 'trevor/integration'})
            verification = audit.verify()
            raw = path.read_text(encoding='utf-8')

        self.assertTrue(verification['ok'])
        self.assertEqual(2, verification['events'])
        self.assertEqual(first['event_hash'], second['previous_hash'])
        self.assertNotIn('private-value', raw)
        self.assertNotIn('owner@example.com', raw)
        self.assertIn('[REDACTED_SECRET]', raw)

    def test_tampering_is_detected_and_blocks_append(self):
        from core.audit_chain import HashChainAuditLog

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            audit = HashChainAuditLog(path)
            audit.append('deployment', {'status': 'started'})
            event = json.loads(path.read_text(encoding='utf-8'))
            event['payload']['status'] = 'altered'
            path.write_text(json.dumps(event) + '\n', encoding='utf-8')

            self.assertFalse(audit.verify()['ok'])
            with self.assertRaisesRegex(RuntimeError, 'audit_chain_invalid'):
                audit.append('deployment', {'status': 'finished'})


if __name__ == '__main__':
    unittest.main()

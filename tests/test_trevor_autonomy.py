import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


class TrevorAutonomyTests(unittest.TestCase):
    def test_single_lease_blocks_parallel_task_and_reclaims_stale(self):
        from core.autonomy import AutonomyLease

        now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lease.json'
            first = AutonomyLease(path, ttl_seconds=60, now=lambda: now)
            second = AutonomyLease(path, ttl_seconds=60, now=lambda: now)

            self.assertTrue(first.acquire('worker-a'))
            self.assertFalse(second.acquire('worker-b'))

            stale = json.loads(path.read_text(encoding='utf-8'))
            stale['expires_at'] = (now - timedelta(seconds=1)).isoformat()
            path.write_text(json.dumps(stale), encoding='utf-8')

            self.assertTrue(second.acquire('worker-b'))
            self.assertFalse(first.release('worker-a'))
            self.assertTrue(second.release('worker-b'))

    def test_policy_pauses_and_forbids_high_risk_actions(self):
        from core.autonomy import AutonomyPolicy

        policy = AutonomyPolicy()

        forbidden = policy.evaluate(
            {'category': 'small_feature', 'input': '替我購買服務並變更帳戶'},
            {'user_active': False, 'cpu_percent': 10, 'memory_percent': 20},
        )
        active = policy.evaluate(
            {'category': 'bugfix', 'input': '修正測試'},
            {'user_active': True, 'cpu_percent': 10, 'memory_percent': 20},
        )
        healthy = policy.evaluate(
            {'category': 'bugfix', 'input': '修正測試'},
            {
                'user_active': False,
                'cpu_percent': 10,
                'memory_percent': 20,
                'quota_sufficient': True,
                'services_healthy': True,
            },
        )

        self.assertEqual('forbidden_action', forbidden['reason'])
        self.assertEqual('user_active', active['reason'])
        self.assertTrue(healthy['allowed'])

    def test_queue_claims_one_task_and_canonicalizes_identity(self):
        from core.autonomy import AutonomyQueue

        with tempfile.TemporaryDirectory() as tmp:
            queue = AutonomyQueue(Path(tmp) / 'queue.json')
            first = queue.enqueue('修正測試', capability_mode='coding', priority=2)
            queue.enqueue('整理文件', capability_mode='content', priority=5)

            claimed = queue.claim_next('worker-a')
            second_claim = queue.claim_next('worker-b')

        self.assertEqual(first['id'], claimed['id'])
        self.assertEqual('trevor', claimed['agent'])
        self.assertEqual('崔佛', claimed['role'])
        self.assertIsNone(second_claim)


if __name__ == '__main__':
    unittest.main()

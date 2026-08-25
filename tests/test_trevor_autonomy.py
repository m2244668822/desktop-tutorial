import json
import multiprocessing
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _enqueue_from_process(path: str, index: int) -> None:
    from core.autonomy import AutonomyQueue

    AutonomyQueue(path).enqueue(f'task-{index}', priority=index)


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

    def test_queue_reclaims_a_task_after_its_worker_lease_expires(self):
        from core.autonomy import AutonomyQueue

        current = datetime(2026, 8, 24, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queue.json'
            queue = AutonomyQueue(path, now=lambda: current, claim_ttl_seconds=60)
            first = queue.enqueue('修正測試')
            queue.claim_next('worker-a')
            current += timedelta(seconds=61)

            reclaimed = AutonomyQueue(
                path, now=lambda: current, claim_ttl_seconds=60
            ).claim_next('worker-b')

        self.assertEqual(first['id'], reclaimed['id'])
        self.assertEqual('worker-b', reclaimed['worker_id'])
        self.assertIn('lease_expires_at', reclaimed)

    def test_only_claim_owner_can_renew_or_finish_running_task(self):
        from core.autonomy import AutonomyQueue

        current = datetime(2026, 8, 24, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = AutonomyQueue(
                Path(tmp) / 'queue.json',
                now=lambda: current,
                claim_ttl_seconds=60,
            )
            task = queue.enqueue('長時間維護')
            queue.claim_next('worker-a')

            self.assertFalse(queue.renew_claim(task['id'], 'worker-b'))
            self.assertTrue(queue.renew_claim(task['id'], 'worker-a'))
            current += timedelta(seconds=61)
            reclaimed = queue.claim_next('worker-b')
            self.assertEqual('worker-b', reclaimed['worker_id'])
            self.assertFalse(
                queue.finish(task['id'], worker_id='worker-a', success=True)
            )
            self.assertTrue(
                queue.finish(task['id'], worker_id='worker-b', success=True)
            )

    def test_expired_claim_cannot_be_renewed(self):
        from core.autonomy import AutonomyQueue

        current = datetime(2026, 8, 24, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = AutonomyQueue(
                Path(tmp) / 'queue.json',
                now=lambda: current,
                claim_ttl_seconds=60,
            )
            task = queue.enqueue('不可復活的過期任務')
            queue.claim_next('worker-a')
            current += timedelta(seconds=61)

            renewed = queue.renew_claim(task['id'], 'worker-a')

        self.assertFalse(renewed)

    def test_queue_uses_an_interprocess_lock_for_mutations(self):
        from core.autonomy import AutonomyQueue

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queue.json'
            queue = AutonomyQueue(path)
            context = multiprocessing.get_context('spawn')
            processes = [
                context.Process(
                    target=_enqueue_from_process,
                    args=(str(path), index),
                )
                for index in range(8)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)

            tasks = queue.tasks()

        self.assertEqual(queue.path.with_suffix('.json.lock'), queue.lock_path)
        self.assertTrue(all(process.exitcode == 0 for process in processes))
        self.assertEqual(8, len(tasks))
        self.assertEqual(8, len({task['id'] for task in tasks}))


if __name__ == '__main__':
    unittest.main()

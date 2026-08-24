import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.autonomy import AutonomyQueue


class AutonomyRunnerTests(unittest.TestCase):
    def test_forbidden_task_fails_without_calling_executor(self):
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            task = queue.enqueue('請幫我購買雲端額度', category='maintenance')
            calls = []
            runner = AutonomyRunner(
                data_root,
                executor=lambda claimed: calls.append(claimed) or {'ok': True},
            )

            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )

            stored = {item['id']: item for item in queue.tasks()}[task['id']]
            self.assertEqual('failed', stored['status'])
            self.assertEqual('forbidden_action', stored['error'])
            self.assertEqual([], calls)
            self.assertEqual('rejected', result['status'])

    def test_paused_task_returns_to_pending(self):
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            task = queue.enqueue('補上測試', category='test')
            runner = AutonomyRunner(data_root, executor=lambda claimed: {'ok': True})

            result = runner.evaluate_once(
                {'user_active': True, 'quota_sufficient': True, 'services_healthy': True}
            )

            stored = {item['id']: item for item in queue.tasks()}[task['id']]
            self.assertEqual('pending', stored['status'])
            self.assertEqual('user_active', stored['pause_reason'])
            self.assertEqual('paused', result['status'])

    def test_approved_task_runs_under_single_lease(self):
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            task = queue.enqueue('整理內容', category='content')
            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=lambda claimed: {'task': claimed['id'], 'ok': True},
            )

            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )

            stored = {item['id']: item for item in queue.tasks()}[task['id']]
            self.assertEqual('completed', stored['status'])
            self.assertEqual(task['id'], stored['result']['task'])
            self.assertFalse((data_root / 'autonomy' / 'task.lease').exists())
            self.assertEqual('completed', result['status'])

    def test_long_running_executor_renews_claim_before_expiry(self):
        from core.autonomy import AutonomyConfig
        from core.autonomy_runner import AutonomyRunner

        current = [datetime(2026, 8, 24, tzinfo=timezone.utc)]
        renewed = threading.Event()
        renewal_attempts = []
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue_path = data_root / 'autonomy' / 'task_queue.json'
            queue = AutonomyQueue(
                queue_path,
                now=lambda: current[0],
                claim_ttl_seconds=60,
            )
            task = queue.enqueue('長時間整理', category='content')

            def execute(claimed):
                current[0] += timedelta(seconds=61)
                self.assertTrue(renewed.wait(timeout=1))
                duplicate = AutonomyQueue(
                    queue_path,
                    now=lambda: current[0],
                    claim_ttl_seconds=60,
                ).claim_next('worker-b')
                return {'task': claimed['id'], 'duplicate': duplicate is not None}

            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=execute,
                config=AutonomyConfig(lease_ttl_seconds=60),
                renewal_interval_seconds=0.01,
            )
            runner.queue = queue
            original_renew = runner.queue.renew_claim

            def track_renewal(task_id, worker_id):
                renewal_attempts.append((task_id, worker_id))
                if len(renewal_attempts) == 1:
                    raise OSError('temporary lock interruption')
                result = original_renew(task_id, worker_id)
                renewed.set()
                return result

            runner.queue.renew_claim = track_renewal
            result = runner.evaluate_once(
                {
                    'user_active': False,
                    'quota_sufficient': True,
                    'services_healthy': True,
                }
            )

            stored = {item['id']: item for item in queue.tasks()}[task['id']]

        self.assertEqual('completed', result['status'])
        self.assertFalse(stored['result']['duplicate'])
        self.assertGreaterEqual(len(renewal_attempts), 2)

    def test_renewal_override_is_clamped_below_effective_claim_ttl(self):
        from core.autonomy import AutonomyConfig
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            runner = AutonomyRunner(
                Path(tmp),
                executor=lambda task: {'ok': True},
                config=AutonomyConfig(lease_ttl_seconds=60),
                renewal_interval_seconds=600,
            )

        self.assertLess(runner.renewal_interval_seconds, 60)
        self.assertEqual(20, runner.renewal_interval_seconds)


if __name__ == '__main__':
    unittest.main()

import tempfile
import threading
import time
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

    def test_paused_policy_reports_lease_lost_if_defer_owner_changed(self):
        from core.autonomy_runner import AutonomyRunner

        current = [datetime(2026, 8, 25, tzinfo=timezone.utc)]
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue_path = data_root / 'autonomy' / 'task_queue.json'
            queue = AutonomyQueue(
                queue_path,
                now=lambda: current[0],
                claim_ttl_seconds=60,
            )
            task = queue.enqueue('補上測試', category='test')
            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=lambda claimed: {'ok': True},
            )
            runner.queue = queue

            def evaluate_after_reclaim(claimed, signals):
                current[0] += timedelta(seconds=61)
                reclaimed = AutonomyQueue(
                    queue_path,
                    now=lambda: current[0],
                    claim_ttl_seconds=60,
                ).claim_next('worker-b')
                self.assertEqual(task['id'], reclaimed['id'])
                return {'allowed': False, 'reason': 'user_active'}

            runner.policy.evaluate = evaluate_after_reclaim
            result = runner.evaluate_once(
                {'user_active': True, 'quota_sufficient': True, 'services_healthy': True}
            )
            stored = {item['id']: item for item in queue.tasks()}[task['id']]

        self.assertEqual('lease_lost', result['status'])
        self.assertEqual('task_claim_lost', result['error'])
        self.assertEqual('running', stored['status'])
        self.assertEqual('worker-b', stored['worker_id'])

    def test_rejected_policy_reports_lease_lost_if_finish_owner_changed(self):
        from core.autonomy_runner import AutonomyRunner

        current = [datetime(2026, 8, 25, tzinfo=timezone.utc)]
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue_path = data_root / 'autonomy' / 'task_queue.json'
            queue = AutonomyQueue(
                queue_path,
                now=lambda: current[0],
                claim_ttl_seconds=60,
            )
            task = queue.enqueue('禁止任務', category='maintenance')
            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=lambda claimed: {'ok': True},
            )
            runner.queue = queue

            def reject_after_reclaim(claimed, signals):
                current[0] += timedelta(seconds=61)
                reclaimed = AutonomyQueue(
                    queue_path,
                    now=lambda: current[0],
                    claim_ttl_seconds=60,
                ).claim_next('worker-b')
                self.assertEqual(task['id'], reclaimed['id'])
                return {'allowed': False, 'reason': 'forbidden_action'}

            runner.policy.evaluate = reject_after_reclaim
            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )
            stored = {item['id']: item for item in queue.tasks()}[task['id']]

        self.assertEqual('lease_lost', result['status'])
        self.assertEqual('task_claim_lost', result['error'])
        self.assertEqual('running', stored['status'])
        self.assertEqual('worker-b', stored['worker_id'])

    def test_claim_loss_cancels_cooperative_executor_before_side_effect(self):
        from core.autonomy_runner import AutonomyRunner

        current = [datetime(2026, 8, 25, tzinfo=timezone.utc)]
        executor_started = threading.Event()
        side_effects = []
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue_path = data_root / 'autonomy' / 'task_queue.json'
            queue = AutonomyQueue(
                queue_path,
                now=lambda: current[0],
                claim_ttl_seconds=60,
            )
            task = queue.enqueue('長時間整理', category='content')

            def execute(claimed, *, cancellation):
                executor_started.set()
                self.assertTrue(cancellation.wait(timeout=1))
                cancellation.raise_if_lost()
                side_effects.append(claimed['id'])
                return {'ok': True}

            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=execute,
                renewal_interval_seconds=0.01,
            )
            runner.queue = queue
            original_renew = queue.renew_claim

            def lose_claim(task_id, worker_id):
                self.assertTrue(executor_started.wait(timeout=1))
                current[0] += timedelta(seconds=61)
                reclaimed = AutonomyQueue(
                    queue_path,
                    now=lambda: current[0],
                    claim_ttl_seconds=60,
                ).claim_next('worker-b')
                self.assertEqual(task['id'], reclaimed['id'])
                return original_renew(task_id, worker_id)

            queue.renew_claim = lose_claim
            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )
            stored = {item['id']: item for item in queue.tasks()}[task['id']]

        self.assertEqual('lease_lost', result['status'])
        self.assertEqual([], side_effects)
        self.assertEqual('worker-b', stored['worker_id'])

    def test_executor_task_echo_remains_json_serializable(self):
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            task = queue.enqueue('回傳任務內容', category='content')
            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=lambda claimed: {'task': claimed},
            )

            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )
            stored = {item['id']: item for item in queue.tasks()}[task['id']]

        self.assertEqual('completed', result['status'])
        self.assertEqual(task['id'], stored['result']['task']['id'])
        self.assertNotIn('_claim_cancellation', stored['result']['task'])

    def test_non_serializable_executor_result_fails_task_cleanly(self):
        from core.autonomy_runner import AutonomyRunner

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            task = queue.enqueue('回傳無法序列化資料', category='content')
            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=lambda claimed: {'value': object()},
            )

            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )
            stored = {item['id']: item for item in queue.tasks()}[task['id']]

        self.assertEqual('failed', result['status'])
        self.assertEqual('failed', stored['status'])
        self.assertIn('executor_result_not_serializable', stored['error'])

    def test_repeated_renewal_errors_cancel_after_claim_ttl(self):
        from core.autonomy_runner import AutonomyRunner

        side_effects = []
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            queue.claim_ttl_seconds = 0.05
            queue.enqueue('長時間整理', category='content')

            def execute(claimed, *, cancellation):
                if not cancellation.wait(timeout=0.5):
                    side_effects.append(claimed['id'])
                    return {'ok': True}
                cancellation.raise_if_lost()

            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=execute,
                renewal_interval_seconds=0.01,
            )
            runner.queue = queue
            runner.queue.renew_claim = lambda task_id, worker_id: (_ for _ in ()).throw(
                OSError('queue temporarily unavailable')
            )
            started = time.monotonic()
            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )
            elapsed = time.monotonic() - started

        self.assertEqual('lease_lost', result['status'])
        self.assertEqual([], side_effects)
        self.assertLess(elapsed, 0.5)

    def test_renewal_wait_never_crosses_confirmed_deadline(self):
        from core.autonomy_runner import AutonomyRunner

        renewals = []
        side_effects = []
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            queue = AutonomyQueue(data_root / 'autonomy' / 'task_queue.json')
            queue.claim_ttl_seconds = 0.05
            queue.enqueue('短租約長任務', category='content')

            def execute(claimed, *, cancellation):
                if not cancellation.wait(timeout=0.3):
                    side_effects.append(claimed['id'])
                    return {'ok': True}
                cancellation.raise_if_lost()

            runner = AutonomyRunner(
                data_root,
                worker_id='worker-a',
                executor=execute,
                renewal_interval_seconds=0.2,
            )
            runner.queue = queue
            runner.queue.renew_claim = lambda task_id, worker_id: (
                renewals.append((task_id, worker_id)) or True
            )

            result = runner.evaluate_once(
                {'user_active': False, 'quota_sufficient': True, 'services_healthy': True}
            )

        self.assertEqual('lease_lost', result['status'])
        self.assertEqual([], renewals)
        self.assertEqual([], side_effects)

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
                current[0] += timedelta(seconds=40)
                self.assertTrue(renewed.wait(timeout=1))
                current[0] += timedelta(seconds=21)
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

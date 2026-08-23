import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main()

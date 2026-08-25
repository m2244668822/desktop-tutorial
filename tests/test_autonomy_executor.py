import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


def _git(cwd, *args):
    return subprocess.run(
        ['git', *args], cwd=cwd, check=True, capture_output=True, text=True
    )


class AutonomyExecutorTests(unittest.TestCase):
    @staticmethod
    def _repository(tmp):
        root = Path(tmp) / 'repo'
        root.mkdir()
        _git(root, 'init')
        _git(root, 'config', 'user.email', 'test@example.invalid')
        _git(root, 'config', 'user.name', 'Trevor Test')
        (root / 'README.md').write_text('initial\n', encoding='utf-8')
        _git(root, 'add', 'README.md')
        _git(root, 'commit', '-m', 'initial')
        _git(root, 'branch', '-M', 'trevor/integration')
        return root

    def test_code_task_merges_only_after_validation(self):
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)

            def workflow(workspace, capability_mode, instruction):
                Path(workspace, 'README.md').write_text('autonomous\n', encoding='utf-8')
                return {
                    'task_state': {
                        'task_id': 'workflow-1',
                        'overall_status': 'success',
                        'completed_steps': 1,
                        'failed_steps': 0,
                    }
                }

            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                workflow=workflow,
                test_commands=(),
            )
            result = executor(
                {
                    'id': 'trevor-task-1',
                    'category': 'bugfix',
                    'capability_mode': 'coding',
                    'input': '修正語法',
                }
            )

            self.assertEqual('merged', result['git']['status'])
            self.assertEqual('autonomous\n', (root / 'README.md').read_text(encoding='utf-8'))
            self.assertEqual([], list((Path(tmp) / 'data' / 'worktrees').glob('*')))

    def test_reclaimed_code_task_uses_claim_unique_worktree_resources(self):
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            attempts = []

            def workflow(workspace, capability_mode, instruction):
                attempts.append(instruction)
                Path(workspace, 'README.md').write_text(
                    f'attempt {len(attempts)}\n', encoding='utf-8'
                )
                return {
                    'task_state': {
                        'task_id': instruction,
                        'overall_status': 'success',
                        'completed_steps': 1,
                        'failed_steps': 0,
                    }
                }

            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                workflow=workflow,
                test_commands=(),
            )
            first = executor(
                {
                    'id': 'trevor-reclaimed-task',
                    'claim_attempt_id': 'attempt-one',
                    'category': 'bugfix',
                    'capability_mode': 'coding',
                    'input': 'same reclaimed task',
                }
            )
            second = executor(
                {
                    'id': 'trevor-reclaimed-task',
                    'claim_attempt_id': 'attempt-two',
                    'category': 'bugfix',
                    'capability_mode': 'coding',
                    'input': 'same reclaimed task',
                }
            )

        self.assertNotEqual(first['git']['branch'], second['git']['branch'])

    def test_content_task_uses_external_data_without_git_worktree(self):
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            called = []

            def workflow(workspace, capability_mode, instruction):
                called.append((Path(workspace), capability_mode, instruction))
                return {
                    'task_state': {
                        'task_id': 'workflow-2',
                        'overall_status': 'success',
                        'completed_steps': 1,
                        'failed_steps': 0,
                    }
                }

            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                workflow=workflow,
                test_commands=(),
            )
            result = executor(
                {
                    'id': 'trevor-task-2',
                    'category': 'content',
                    'capability_mode': 'content',
                    'input': '整理內容',
                }
            )

            self.assertEqual(root.resolve(), called[0][0])
            self.assertEqual('completed', result['status'])
            self.assertFalse((Path(tmp) / 'data' / 'worktrees').exists())

    def test_code_task_does_not_merge_after_claim_cancellation(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            cancellation = ClaimCancellation()

            def workflow(workspace, capability_mode, instruction):
                Path(workspace, 'README.md').write_text('stale worker\n', encoding='utf-8')
                cancellation.mark_lost()
                return {
                    'task_state': {
                        'task_id': 'workflow-cancelled',
                        'overall_status': 'success',
                        'completed_steps': 1,
                        'failed_steps': 0,
                    }
                }

            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                workflow=workflow,
                test_commands=(),
            )
            with self.assertRaises(ClaimLostError):
                executor(
                    {
                        'id': 'trevor-task-cancelled',
                        'category': 'bugfix',
                        'capability_mode': 'coding',
                        'input': '過期任務',
                    },
                    cancellation=cancellation,
                )

            self.assertEqual(
                'initial\n',
                (root / 'README.md').read_text(encoding='utf-8'),
            )

    def test_validation_subprocess_stops_after_claim_cancellation(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            cancellation = ClaimCancellation()
            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                test_commands=(
                    (sys.executable, '-c', 'import time; time.sleep(1)'),
                ),
            )
            timer = threading.Timer(0.05, cancellation.mark_lost)
            started = time.monotonic()
            timer.start()
            try:
                with self.assertRaises(ClaimLostError):
                    executor._validate(root, cancellation)
            finally:
                timer.cancel()
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.8)

    def test_validation_cancellation_terminates_subprocess_tree(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            marker = Path(tmp) / 'stale-child-side-effect'
            child_code = (
                'import time; from pathlib import Path; '
                f'time.sleep(0.25); Path({str(marker)!r}).write_text("stale")'
            )
            parent_code = (
                'import subprocess, sys, time; '
                f'subprocess.Popen([sys.executable, "-c", {child_code!r}], '
                'stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); '
                'time.sleep(5)'
            )
            cancellation = ClaimCancellation()
            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                test_commands=((sys.executable, '-c', parent_code),),
            )
            timer = threading.Timer(0.05, cancellation.mark_lost)
            timer.start()
            try:
                with self.assertRaises(ClaimLostError):
                    executor._validate(root, cancellation)
            finally:
                timer.cancel()
            time.sleep(0.35)

            self.assertFalse(marker.exists())

    def test_validation_cancellation_kills_sigterm_ignoring_descendant(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            marker = Path(tmp) / 'sigterm-ignoring-child-side-effect'
            ready = Path(tmp) / 'sigterm-ignoring-child-ready'
            child_script = (
                "trap '' TERM; "
                f"printf ready > {shlex.quote(str(ready))}; "
                "sleep 0.6; "
                f"printf stale > {shlex.quote(str(marker))}"
            )
            parent_script = (
                f"/bin/sh -c {shlex.quote(child_script)} >/dev/null 2>&1 & "
                "sleep 5"
            )
            cancellation = ClaimCancellation()
            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                test_commands=(),
            )

            def cancel_when_descendant_is_ready():
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if ready.exists():
                        cancellation.mark_lost()
                        return
                    time.sleep(0.01)

            canceller = threading.Thread(target=cancel_when_descendant_is_ready)
            canceller.start()
            try:
                with self.assertRaises(ClaimLostError):
                    executor._run_validation_command(
                        ('/bin/sh', '-c', parent_script),
                        root,
                        cancellation,
                    )
            finally:
                canceller.join(timeout=2)
            time.sleep(0.7)

            self.assertFalse(marker.exists())

    def test_variadic_workflow_receives_cancel_check(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.autonomy_executor import TrevorTaskExecutor

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            cancellation = ClaimCancellation()

            def workflow(*args, **kwargs):
                cancellation.mark_lost()
                kwargs['cancel_check']()

            executor = TrevorTaskExecutor(
                root,
                Path(tmp) / 'data',
                workflow=workflow,
                test_commands=(),
            )
            with self.assertRaises(ClaimLostError):
                executor(
                    {
                        'id': 'trevor-variadic-workflow',
                        'category': 'content',
                        'capability_mode': 'content',
                        'input': '取消包裝 workflow',
                    },
                    cancellation=cancellation,
                )

    def test_process_group_is_not_signaled_after_final_probe_disappears(self):
        import signal

        from core.autonomy_executor import TrevorTaskExecutor

        class FinishedProcess:
            pid = 424242

            @staticmethod
            def poll():
                return 0

            @staticmethod
            def communicate(timeout=None):
                return '', ''

        signals = []

        def signal_group(process_group, requested_signal):
            signals.append(requested_signal)
            if requested_signal == 0:
                raise ProcessLookupError
            if requested_signal == signal.SIGKILL:
                self.fail('disappeared process group must not receive SIGKILL')

        with patch('core.autonomy_executor.os.killpg', side_effect=signal_group):
            TrevorTaskExecutor._terminate_process_tree(FinishedProcess())

        self.assertEqual([signal.SIGTERM, 0], signals)


if __name__ == '__main__':
    unittest.main()

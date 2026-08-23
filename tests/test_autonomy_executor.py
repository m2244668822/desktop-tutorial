import subprocess
import tempfile
import unittest
from pathlib import Path


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


if __name__ == '__main__':
    unittest.main()

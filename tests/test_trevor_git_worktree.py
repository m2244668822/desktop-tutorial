import subprocess
import tempfile
import unittest
from pathlib import Path


def _git(cwd, *args):
    return subprocess.run(
        ['git', *args], cwd=cwd, check=True, capture_output=True, text=True
    )


class TrevorGitWorktreeTests(unittest.TestCase):
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

    def test_task_worktree_uses_required_branch_namespace(self):
        from core.git_worktree import TrevorWorktreeManager

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)

            manager = TrevorWorktreeManager(root, Path(tmp) / 'data')
            created = manager.create('task-123', 'Fix syntax now')

            branch = _git(created['path'], 'branch', '--show-current').stdout.strip()
            listed = _git(root, 'worktree', 'list', '--porcelain').stdout

        self.assertEqual('trevor/task/task-123-fix-syntax-now', created['branch'])
        self.assertEqual(created['branch'], branch)
        self.assertIn(str(created['path']), listed)

    def test_creation_requires_clean_integration_branch(self):
        from core.git_worktree import TrevorWorktreeManager

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            (root / 'README.md').write_text('dirty\n', encoding='utf-8')

            manager = TrevorWorktreeManager(root, Path(tmp) / 'data')
            with self.assertRaisesRegex(RuntimeError, 'integration_worktree_dirty'):
                manager.create('task-1', 'dirty')

    def test_finalize_merges_validated_change_and_removes_worktree(self):
        from core.git_worktree import TrevorWorktreeManager

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            manager = TrevorWorktreeManager(root, Path(tmp) / 'data')
            created = manager.create('task-2', 'update readme')
            created['path'].joinpath('README.md').write_text('updated\n', encoding='utf-8')

            result = manager.finalize(
                created,
                commit_message='feat: update readme',
                validator=lambda path: {'ok': True, 'path': str(path)},
            )

            self.assertEqual('merged', result['status'])
            self.assertEqual('updated\n', (root / 'README.md').read_text(encoding='utf-8'))
            self.assertFalse(created['path'].exists())
            self.assertIn('Merge branch', _git(root, 'log', '-1', '--pretty=%s').stdout)

    def test_finalize_keeps_failed_worktree_isolated(self):
        from core.git_worktree import TrevorWorktreeManager

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            manager = TrevorWorktreeManager(root, Path(tmp) / 'data')
            created = manager.create('task-3', 'unsafe change')
            created['path'].joinpath('README.md').write_text('unsafe\n', encoding='utf-8')

            with self.assertRaisesRegex(RuntimeError, 'validation_failed'):
                manager.finalize(
                    created,
                    commit_message='feat: unsafe',
                    validator=lambda path: {'ok': False, 'findings': [{'path': str(path)}]},
                )

            self.assertEqual('initial\n', (root / 'README.md').read_text(encoding='utf-8'))
            self.assertTrue(created['path'].exists())

    def test_finalize_does_not_merge_after_claim_cancellation(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.git_worktree import TrevorWorktreeManager

        with tempfile.TemporaryDirectory() as tmp:
            root = self._repository(tmp)
            manager = TrevorWorktreeManager(root, Path(tmp) / 'data')
            created = manager.create('task-4', 'cancelled change')
            created['path'].joinpath('README.md').write_text(
                'cancelled\n', encoding='utf-8'
            )
            cancellation = ClaimCancellation()

            def validate(path):
                cancellation.mark_lost()
                return {'ok': True, 'path': str(path)}

            with self.assertRaises(ClaimLostError):
                manager.finalize(
                    created,
                    commit_message='feat: cancelled',
                    validator=validate,
                    cancel_check=cancellation.raise_if_lost,
                )

            self.assertEqual('initial\n', (root / 'README.md').read_text(encoding='utf-8'))
            self.assertTrue(created['path'].exists())


if __name__ == '__main__':
    unittest.main()

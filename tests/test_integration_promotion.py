import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class _Runner:
    def __init__(self, *, branch='trevor/integration', status='', pull_requests=None):
        self.branch = branch
        self.status = status
        self.pull_requests = pull_requests if pull_requests is not None else []
        self.calls = []

    def __call__(self, command, **kwargs):
        args = [str(value) for value in command]
        self.calls.append(args)
        stdout = ''
        if args[:3] == ['git', 'branch', '--show-current']:
            stdout = self.branch + '\n'
        elif args[:3] == ['git', 'status', '--porcelain']:
            stdout = self.status
        elif args[:3] == ['gh', 'pr', 'list']:
            stdout = json.dumps(self.pull_requests)
        elif args[:3] == ['gh', 'pr', 'create']:
            stdout = 'https://github.com/example/repo/pull/9\n'
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr='')


class IntegrationPromotionTests(unittest.TestCase):
    def test_clean_integration_pushes_creates_pr_and_enables_merge_commit(self):
        from core.integration_promotion import TrevorIntegrationPromoter

        runner = _Runner()
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / 'repo'
            repository.mkdir()
            result = TrevorIntegrationPromoter(
                repository,
                Path(tmp) / 'data',
                runner=runner,
                validation_commands=(),
            ).promote(title='Trevor integration')

        self.assertTrue(result['ok'])
        self.assertTrue(result['created'])
        self.assertEqual('https://github.com/example/repo/pull/9', result['pull_request'])
        self.assertIn(['git', 'push', 'origin', 'trevor/integration'], runner.calls)
        self.assertIn(
            [
                'gh',
                'pr',
                'merge',
                'https://github.com/example/repo/pull/9',
                '--auto',
                '--merge',
            ],
            runner.calls,
        )

    def test_existing_pr_is_reused(self):
        from core.integration_promotion import TrevorIntegrationPromoter

        runner = _Runner(
            pull_requests=[{'number': 4, 'url': 'https://github.com/example/repo/pull/4'}]
        )
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / 'repo'
            repository.mkdir()
            result = TrevorIntegrationPromoter(
                repository,
                Path(tmp) / 'data',
                runner=runner,
                validation_commands=(),
            ).promote()

        self.assertFalse(result['created'])
        self.assertEqual('https://github.com/example/repo/pull/4', result['pull_request'])
        self.assertFalse(any(call[:3] == ['gh', 'pr', 'create'] for call in runner.calls))

    def test_dirty_or_wrong_branch_is_blocked_before_push(self):
        from core.integration_promotion import TrevorIntegrationPromoter

        for runner, error in (
            (_Runner(branch='main'), 'integration_branch_required'),
            (_Runner(status=' M unsafe.py\n'), 'integration_worktree_dirty'),
        ):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                repository = Path(tmp) / 'repo'
                repository.mkdir()
                promoter = TrevorIntegrationPromoter(
                    repository,
                    Path(tmp) / 'data',
                    runner=runner,
                    validation_commands=(),
                )
                with self.assertRaisesRegex(RuntimeError, error):
                    promoter.promote()
                self.assertFalse(any(call[:2] == ['git', 'push'] for call in runner.calls))


if __name__ == '__main__':
    unittest.main()

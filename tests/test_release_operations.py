import subprocess
import tempfile
import unittest
from pathlib import Path


def _git(repository, *arguments):
    return subprocess.run(
        ['git', *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class TrevorReleaseOperationsTests(unittest.TestCase):
    @staticmethod
    def _repository(directory):
        repository = Path(directory) / 'repository'
        repository.mkdir()
        _git(repository, 'init')
        _git(repository, 'config', 'user.email', 'trevor@example.invalid')
        _git(repository, 'config', 'user.name', 'Trevor Test')
        (repository / 'state.txt').write_text('before\n', encoding='utf-8')
        _git(repository, 'add', 'state.txt')
        _git(repository, 'commit', '-m', 'initial')
        _git(repository, 'branch', '-M', 'trevor/integration')
        (repository / 'state.txt').write_text('after\n', encoding='utf-8')
        _git(repository, 'commit', '-am', 'change to revert')
        return repository

    def test_operation_audit_accepts_only_required_event_types(self):
        from core.release_operations import record_operation

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / 'data'
            event = record_operation(
                data_root,
                'deployment',
                status='completed',
                subject='oci-systemd',
                details={'host': 'private.example'},
            )

            with self.assertRaisesRegex(ValueError, 'unsupported_operation_event'):
                record_operation(data_root, 'arbitrary', status='completed')

        self.assertEqual('deployment', event['event_type'])
        self.assertEqual('completed', event['payload']['status'])
        self.assertEqual('oci-systemd', event['payload']['subject'])

    def test_git_revert_rollback_is_clean_and_hash_chain_audited(self):
        from core.audit_chain import HashChainAuditLog
        from core.release_operations import revert_commit

        with tempfile.TemporaryDirectory() as tmp:
            repository = self._repository(tmp)
            data_root = Path(tmp) / 'data'
            target = _git(repository, 'rev-parse', 'HEAD')

            result = revert_commit(
                repository,
                target,
                data_root=data_root,
                reason='regression',
            )
            events = HashChainAuditLog(
                data_root / 'audit' / 'events.jsonl'
            ).read(limit=10)

            self.assertEqual('before\n', (repository / 'state.txt').read_text())
            self.assertEqual('', _git(repository, 'status', '--porcelain'))
            self.assertNotEqual(target, result['result_commit'])
            self.assertEqual(['started', 'completed'], [
                event['payload']['status'] for event in events
            ])
            self.assertTrue(HashChainAuditLog(
                data_root / 'audit' / 'events.jsonl'
            ).verify()['ok'])


if __name__ == '__main__':
    unittest.main()

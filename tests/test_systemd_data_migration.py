import os
import pwd
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'deploy' / 'systemd' / 'install.sh'


def _migration_source() -> str:
    content = INSTALLER.read_text(encoding='utf-8')
    start_marker = "<<'PY_MIGRATE_TREVOR_DATA'\n"
    end_marker = '\nPY_MIGRATE_TREVOR_DATA\n'
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


@unittest.skipUnless(os.name == 'posix', 'descriptor-relative migration is POSIX-only')
class SystemdDataMigrationTests(unittest.TestCase):
    def _run_migration(self, data_root: Path) -> subprocess.CompletedProcess[str]:
        user_name = pwd.getpwuid(os.getuid()).pw_name
        return subprocess.run(
            [sys.executable, '-', str(data_root), user_name],
            input=_migration_source(),
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )

    def test_migrates_legacy_auth_and_audit_without_replacing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / 'data'
            auth_root = data_root / 'auth'
            audit_root = data_root / 'audit'
            auth_root.mkdir(parents=True)
            audit_root.mkdir()
            key_store = auth_root / 'api_keys.json'
            audit_log = audit_root / 'events.jsonl'
            key_store.write_text('{"schema_version": 1}\n', encoding='utf-8')
            audit_log.write_text('{"event": "legacy"}\n', encoding='utf-8')
            auth_root.chmod(0o755)
            audit_root.chmod(0o755)
            key_store.chmod(0o644)
            audit_log.chmod(0o644)

            result = self._run_migration(data_root)

            self.assertEqual('', result.stderr)
            self.assertEqual(0, result.returncode)
            self.assertEqual(0o700, stat.S_IMODE(auth_root.stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE(audit_root.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE(key_store.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE(audit_log.stat().st_mode))
            self.assertEqual(
                '{"schema_version": 1}\n',
                key_store.read_text(encoding='utf-8'),
            )
            self.assertEqual(
                '{"event": "legacy"}\n',
                audit_log.read_text(encoding='utf-8'),
            )

    def test_rejects_symlinked_auth_directory_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / 'data'
            outside = root / 'outside'
            data_root.mkdir()
            outside.mkdir()
            outside.chmod(0o755)
            (data_root / 'auth').symlink_to(outside, target_is_directory=True)

            result = self._run_migration(data_root)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(0o755, stat.S_IMODE(outside.stat().st_mode))

    def test_rejects_hardlinked_store_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / 'data'
            auth_root = data_root / 'auth'
            auth_root.mkdir(parents=True)
            outside = root / 'outside.json'
            outside.write_text('{}\n', encoding='utf-8')
            outside.chmod(0o644)
            os.link(outside, auth_root / 'api_keys.json')

            result = self._run_migration(data_root)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(0o644, stat.S_IMODE(outside.stat().st_mode))

    def test_rejects_fifo_store_without_blocking_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / 'data'
            auth_root = data_root / 'auth'
            auth_root.mkdir(parents=True)
            os.mkfifo(auth_root / 'api_keys.json')

            result = self._run_migration(data_root)

            self.assertNotEqual(0, result.returncode)


if __name__ == '__main__':
    unittest.main()

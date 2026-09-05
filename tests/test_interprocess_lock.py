import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class InterprocessLockTests(unittest.TestCase):
    def test_windows_backend_uses_msvcrt_without_unix_fchmod(self):
        from core.interprocess_lock import exclusive_file_lock

        class FakeMsvcrt:
            LK_NBLCK = 1
            LK_UNLCK = 2

            def __init__(self):
                self.calls = []

            def locking(self, descriptor, mode, size):
                self.calls.append((descriptor, mode, size))

        backend = FakeMsvcrt()
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / 'windows-compatible.lock'
            with patch('core.interprocess_lock.fcntl', None), patch(
                'core.interprocess_lock.msvcrt', backend
            ), patch(
                'core.interprocess_lock.os.fchmod',
                side_effect=AssertionError('Unix-only fchmod must not run'),
            ):
                with exclusive_file_lock(lock_path):
                    self.assertTrue(lock_path.exists())

        self.assertEqual(backend.LK_NBLCK, backend.calls[0][1])
        self.assertEqual(backend.LK_UNLCK, backend.calls[-1][1])
        self.assertTrue(all(size == 1 for _, _, size in backend.calls))


if __name__ == '__main__':
    unittest.main()

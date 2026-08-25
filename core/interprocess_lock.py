from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


_THREAD_LOCK = threading.Lock()


def _lock_windows(descriptor: int) -> None:
    if msvcrt is None:
        raise RuntimeError('interprocess_lock_backend_unavailable')
    if os.fstat(descriptor).st_size < 1:
        os.write(descriptor, b'\0')
        os.fsync(descriptor)
    while True:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            time.sleep(0.05)


def _unlock_windows(descriptor: int) -> None:
    if msvcrt is None:
        return
    os.lseek(descriptor, 0, os.SEEK_SET)
    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


@contextmanager
def exclusive_file_lock(path: str | Path):
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with _THREAD_LOCK:
            if fcntl is not None:
                if hasattr(os, 'fchmod'):
                    os.fchmod(descriptor, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            elif msvcrt is not None:
                _lock_windows(descriptor)
                try:
                    yield
                finally:
                    _unlock_windows(descriptor)
            else:
                raise RuntimeError('interprocess_lock_backend_unavailable')
    finally:
        os.close(descriptor)


__all__ = ['exclusive_file_lock']

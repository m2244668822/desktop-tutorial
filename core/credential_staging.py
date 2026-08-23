from __future__ import annotations

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping


_CREDENTIAL_NAME = re.compile(r'^[a-z0-9][a-z0-9_-]*$')


@contextmanager
def staged_credentials(
    credentials: Mapping[str, str],
    *,
    parent: str | Path | None = None,
) -> Iterator[Path]:
    normalized: dict[str, str] = {}
    for name, value in credentials.items():
        credential_name = str(name or '').strip().lower()
        if not _CREDENTIAL_NAME.fullmatch(credential_name):
            raise ValueError('invalid_credential_name')
        credential_value = str(value or '').strip()
        if not credential_value:
            raise ValueError('empty_credential')
        normalized[credential_name] = credential_value

    parent_path = Path(parent).expanduser() if parent is not None else None
    if parent_path is not None:
        parent_path.mkdir(parents=True, exist_ok=True)
        os.chmod(parent_path, 0o700)
    directory = Path(
        tempfile.mkdtemp(
            prefix='trevor-credentials-',
            dir=str(parent_path) if parent_path is not None else None,
        )
    )
    os.chmod(directory, 0o700)
    try:
        for name, value in normalized.items():
            path = directory / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            try:
                os.write(descriptor, value.encode('utf-8'))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.chmod(path, 0o400)
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


__all__ = ['staged_credentials']

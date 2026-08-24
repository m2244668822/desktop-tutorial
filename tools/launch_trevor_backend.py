#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.credential_staging import staged_credentials
from core.data_paths import resolve_data_root
from core.keychain_credentials import KeychainCredentialStore


CREDENTIAL_SPECS = (
    ('nvidia_api_key', 'trevor.providers', 'nvidia-api-key'),
    ('gemini_api_key', 'trevor.providers', 'gemini-api-key'),
    ('groq_api_key', 'trevor.providers', 'groq-api-key'),
    ('cerebras_api_key', 'trevor.providers', 'cerebras-api-key'),
    ('openrouter_api_key', 'trevor.providers', 'openrouter-api-key'),
    ('cloudflare_api_key', 'trevor.providers', 'cloudflare-api-key'),
    ('trevor_api_hmac', 'trevor.auth', 'api-key-hmac'),
    ('trevor_memory_key_b64', 'trevor.memory', 'aes-256-gcm'),
    ('ai_horde_api_key', 'perob.ai-horde', 'api-key'),
)


def runtime_python_path(python_executable: str) -> Path:
    return Path(python_executable).expanduser().absolute()


def collect_runtime_credentials(store: KeychainCredentialStore | Any) -> dict[str, str]:
    credentials: dict[str, str] = {}
    for credential_name, service, account in CREDENTIAL_SPECS:
        result = store.get_secret(service, account)
        if result.configured:
            credentials[credential_name] = result.value
    return credentials


def _read_private_credential(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return ''
    except OSError as exc:
        raise RuntimeError('credential_file_unreadable') from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError('credential_file_invalid')
        if metadata.st_uid != os.getuid():
            raise RuntimeError('credential_file_owner')
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError('credential_file_permissions')
        with os.fdopen(descriptor, 'r', encoding='utf-8', closefd=False) as handle:
            value = handle.read(1024 * 1024 + 1)
        if len(value) > 1024 * 1024:
            raise RuntimeError('credential_file_too_large')
        return value.strip()
    finally:
        os.close(descriptor)


def load_runtime_credentials(
    source_directory: str | Path,
    *,
    allow_keychain: bool = False,
) -> dict[str, str]:
    directory = Path(source_directory).expanduser()
    credentials: dict[str, str] = {}
    if directory.exists():
        metadata = directory.lstat()
        if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError('credential_directory_invalid')
        if metadata.st_uid != os.getuid():
            raise RuntimeError('credential_directory_owner')
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError('credential_directory_permissions')
        for credential_name, _service, _account in CREDENTIAL_SPECS:
            value = _read_private_credential(directory / credential_name)
            if value:
                credentials[credential_name] = value
    if allow_keychain:
        keychain_credentials = collect_runtime_credentials(KeychainCredentialStore())
        for credential_name, value in keychain_credentials.items():
            credentials.setdefault(credential_name, value)
    return credentials


def run_backend(
    python_executable: str,
    command: list[str],
    *,
    credential_source: str | Path | None = None,
    allow_keychain: bool = False,
) -> int:
    runtime_python = runtime_python_path(python_executable)
    if not runtime_python.is_file():
        raise RuntimeError('runtime_python_missing')
    if not command:
        raise RuntimeError('backend_command_missing')
    data_root = resolve_data_root(ROOT)
    source_directory = credential_source or os.getenv(
        'TREVOR_CREDENTIAL_SOURCE_DIR',
        str(data_root / 'credentials'),
    )
    credentials = load_runtime_credentials(
        source_directory,
        allow_keychain=allow_keychain,
    )
    run_root = data_root / 'run'
    environment = os.environ.copy()
    for name in (
        'NVIDIA_API_KEY',
        'NVAPI_API_KEY',
        'GEMINI_API_KEY',
        'GROQ_API_KEY',
        'CEREBRAS_API_KEY',
        'OPENROUTER_API_KEY',
        'CLOUDFLARE_API_TOKEN',
        'AI_HORDE_API_KEY',
        'TREVOR_MEMORY_KEY_B64',
    ):
        environment.pop(name, None)
    environment.pop('TREVOR_CREDENTIAL_SOURCE_DIR', None)
    with staged_credentials(credentials, parent=run_root) as credential_directory:
        environment['CREDENTIALS_DIRECTORY'] = str(credential_directory)
        environment['TREVOR_DATA_DIR'] = str(data_root)
        environment['TREVOR_DISABLE_KEYCHAIN'] = 'true'
        process = subprocess.Popen(
            [str(runtime_python), *command],
            cwd=str(ROOT),
            env=environment,
        )

        def forward(signal_number: int, _frame: Any) -> None:
            if process.poll() is None:
                process.send_signal(signal_number)

        signal.signal(signal.SIGTERM, forward)
        signal.signal(signal.SIGINT, forward)
        return int(process.wait() or 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Launch Trevor with staged non-interactive credentials'
    )
    parser.add_argument('--python', required=True)
    parser.add_argument('--credential-source')
    parser.add_argument(
        '--allow-keychain',
        action='store_true',
        help='explicitly import missing credentials from macOS Keychain; may require approval',
    )
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == '--':
        command = command[1:]
    try:
        return run_backend(
            args.python,
            command,
            credential_source=args.credential_source,
            allow_keychain=args.allow_keychain,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
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


def run_backend(python_executable: str, command: list[str]) -> int:
    runtime_python = runtime_python_path(python_executable)
    if not runtime_python.is_file():
        raise RuntimeError('runtime_python_missing')
    if not command:
        raise RuntimeError('backend_command_missing')
    credentials = collect_runtime_credentials(KeychainCredentialStore())
    run_root = resolve_data_root(ROOT) / 'run'
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
    with staged_credentials(credentials, parent=run_root) as credential_directory:
        environment['CREDENTIALS_DIRECTORY'] = str(credential_directory)
        environment['TREVOR_DATA_DIR'] = str(resolve_data_root(ROOT))
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
    parser = argparse.ArgumentParser(description='Launch Trevor with staged Keychain credentials')
    parser.add_argument('--python', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == '--':
        command = command[1:]
    try:
        return run_backend(args.python, command)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

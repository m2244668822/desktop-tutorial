#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.credential_staging import staged_credentials
from core.data_paths import resolve_data_root
from core.keychain_credentials import KeychainCredentialStore


def load_graphiti_credentials(
    credential_store: KeychainCredentialStore | Any | None = None,
) -> dict[str, str]:
    store = credential_store or KeychainCredentialStore()
    gemini = store.get_secret('trevor.providers', 'gemini-api-key')
    nvidia = store.get_secret('trevor.providers', 'nvidia-api-key')
    if not gemini.configured and not nvidia.configured:
        raise RuntimeError('graphiti_llm_credential_missing')
    internal_token = store.get_secret('trevor.providers', 'graphiti-token')
    if not internal_token.configured:
        raise RuntimeError('graphiti_token_missing')
    return {
        'gemini_api_key': gemini.value if gemini.configured else '',
        'nvidia_api_key': nvidia.value if nvidia.configured else '',
        'graphiti_token': internal_token.value,
    }


def _health_ready(url: str) -> bool:
    try:
        with urllib_request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode('utf-8'))
        return response.status == 200 and bool(payload.get('ok'))
    except (OSError, ValueError, urllib_error.URLError):
        return False


def _atomic_pid(path: Path, process_id: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
    temporary.write_text(f'{process_id}\n', encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def launch(*, wait_seconds: int = 120) -> int:
    executable = ROOT / 'services' / 'graphiti_sidecar' / '.venv' / 'bin' / 'trevor-graphiti'
    if not executable.is_file():
        raise RuntimeError('graphiti_environment_missing')
    credentials = load_graphiti_credentials()
    data_root = resolve_data_root(ROOT)
    run_dir = data_root / 'run'
    run_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(run_dir, 0o700)
    log_dir = Path(
        os.getenv('APP_LOG_DIR', str(Path.home() / 'Library' / 'Logs' / 'Trevor'))
    ).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'graphiti.log'
    pid_path = run_dir / 'graphiti.pid'
    health_url = 'http://127.0.0.1:8091/health'
    child: subprocess.Popen[bytes] | None = None

    with staged_credentials(credentials) as credential_directory:
        environment = os.environ.copy()
        for name in (
            'GEMINI_API_KEY',
            'GOOGLE_API_KEY',
            'NVIDIA_API_KEY',
            'NVAPI_API_KEY',
            'TREVOR_GRAPHITI_TOKEN',
        ):
            environment.pop(name, None)
        environment.update(
            {
                'CREDENTIALS_DIRECTORY': str(credential_directory),
                'GRAPHITI_TELEMETRY_ENABLED': 'false',
                'TREVOR_DATA_DIR': str(data_root),
                'PYTHONUNBUFFERED': '1',
            }
        )
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            child = subprocess.Popen(
                [str(executable)],
                cwd=str(executable.parents[2]),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=descriptor,
                stderr=subprocess.STDOUT,
            )
        finally:
            os.close(descriptor)
        _atomic_pid(pid_path, child.pid)
        deadline = time.monotonic() + max(10, int(wait_seconds))
        while time.monotonic() < deadline:
            if child.poll() is not None:
                pid_path.unlink(missing_ok=True)
                raise RuntimeError('graphiti_start_failed')
            if _health_ready(health_url):
                break
            time.sleep(1)
        else:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
            pid_path.unlink(missing_ok=True)
            raise RuntimeError('graphiti_start_timeout')

    assert child is not None

    def stop_child(_signal_number: int, _frame: Any) -> None:
        if child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)
    print(json.dumps({'ok': True, 'service': 'graphiti', 'pid': child.pid}))
    try:
        return int(child.wait() or 0)
    finally:
        pid_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Launch the private Trevor Graphiti sidecar')
    parser.add_argument('--wait-seconds', type=int, default=120)
    args = parser.parse_args()
    try:
        return launch(wait_seconds=args.wait_seconds)
    except RuntimeError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

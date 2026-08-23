#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_paths import resolve_data_root
from core.edge_client import EncryptedOfflineQueue, TrevorEdgeClient
from core.encrypted_store import AESGCMJsonStore, DeviceEncryptionKey
from core.keychain_credentials import KeychainCredentialStore


def _api_key() -> str:
    result = KeychainCredentialStore().get_secret(
        'trevor.clients', 'local-admin-api-key'
    )
    return result.value if result.configured else ''


def _atomic_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def build_client() -> tuple[TrevorEdgeClient, Path]:
    data_root = resolve_data_root(ROOT)
    remote_url = str(os.getenv('TREVOR_EDGE_REMOTE_URL', 'http://127.0.0.1:5001')).strip()
    key = DeviceEncryptionKey(service='trevor.edge', account='offline-queue-aes')
    queue = EncryptedOfflineQueue(
        data_root / 'edge' / 'offline_queue.json', AESGCMJsonStore(key.get_or_create)
    )
    return TrevorEdgeClient(
        remote_url, queue, api_key_provider=_api_key
    ), data_root / 'edge' / 'status.json'


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trevor encrypted Tailscale edge client')
    parser.add_argument('mode', nargs='?', choices=('daemon', 'heartbeat'), default='daemon')
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--once', action='store_true')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    client, status_path = build_client()
    stop = threading.Event()

    def request_stop(signum: int, frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop.is_set():
        try:
            result = client.heartbeat()
            status = 'connected' if result.get('ok') else 'degraded'
            replay = result.get('replay', {})
        except Exception:
            status = 'offline'
            replay = {'sent': 0, 'failed': 1}
        _atomic_status(
            status_path,
            {
                'schema_version': 1,
                'identity': {'agent': 'trevor', 'role': '崔佛'},
                'status': status,
                'checked_at': datetime.now(timezone.utc).isoformat(),
                'replay': replay,
            },
        )
        if args.mode == 'heartbeat' or args.once:
            break
        stop.wait(max(10, int(args.interval)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

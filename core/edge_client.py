from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import request as urllib_request

from core.encrypted_store import AESGCMJsonStore


Sender = Callable[[str, str, dict[str, Any] | None, dict[str, str]], dict[str, Any]]


class EncryptedOfflineQueue:
    def __init__(self, path: str | Path, store: AESGCMJsonStore) -> None:
        self.path = Path(path)
        self.store = store
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        payload = self.store.read_json(self.path, {'schema_version': 1, 'items': []})
        if not isinstance(payload, dict) or not isinstance(payload.get('items', []), list):
            raise RuntimeError('edge_queue_invalid')
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self.store.write_json(self.path, payload)

    def enqueue(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = {
            'id': str(uuid.uuid4()),
            'endpoint': str(endpoint or '').strip(),
            'payload': dict(payload),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        if not item['endpoint'].startswith('/'):
            raise ValueError('edge_endpoint_invalid')
        with self._lock:
            queue = self._read()
            queue.setdefault('items', []).append(item)
            queue['updated_at'] = item['created_at']
            self._write(queue)
        return dict(item)

    def items(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._read().get('items', []) if isinstance(item, dict)]

    def remove(self, item_ids: set[str]) -> None:
        if not item_ids:
            return
        with self._lock:
            queue = self._read()
            queue['items'] = [
                item
                for item in queue.get('items', [])
                if not isinstance(item, dict) or item.get('id') not in item_ids
            ]
            queue['updated_at'] = datetime.now(timezone.utc).isoformat()
            self._write(queue)


class TrevorEdgeClient:
    def __init__(
        self,
        remote_url: str,
        queue: EncryptedOfflineQueue,
        *,
        api_key_provider: Callable[[], str],
        sender: Sender | None = None,
    ) -> None:
        self.remote_url = str(remote_url or '').rstrip('/')
        if not self.remote_url.startswith(('http://', 'https://')):
            raise ValueError('edge_remote_url_invalid')
        self.queue = queue
        self.api_key_provider = api_key_provider
        self.sender = sender or self._send_json

    @staticmethod
    def _send_json(
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request = urllib_request.Request(
            url,
            data=None if payload is None else json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json', **headers},
            method=method,
        )
        with urllib_request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
        return result if isinstance(result, dict) else {'ok': False}

    def _headers(self) -> dict[str, str]:
        api_key = str(self.api_key_provider() or '').strip()
        if not api_key:
            raise RuntimeError('edge_api_key_unavailable')
        return {'Authorization': f'Bearer {api_key}'}

    def send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = dict(payload)
        try:
            result = self.sender(
                'POST',
                self.remote_url + '/api/send_message',
                request_payload,
                self._headers(),
            )
        except Exception:
            queued = self.queue.enqueue('/api/send_message', request_payload)
            return {'ok': True, 'status': 'queued_offline', 'queue_id': queued['id']}
        return {'ok': bool(result.get('ok', True)), 'status': 'sent', 'response': result}

    def flush(self) -> dict[str, Any]:
        sent_ids: set[str] = set()
        failed = 0
        for item in self.queue.items():
            try:
                result = self.sender(
                    'POST',
                    self.remote_url + str(item.get('endpoint', '')),
                    dict(item.get('payload', {}) or {}),
                    self._headers(),
                )
                if result.get('ok') is False:
                    failed += 1
                    break
            except Exception:
                failed += 1
                break
            sent_ids.add(str(item.get('id', '')))
        self.queue.remove(sent_ids)
        return {'ok': failed == 0, 'sent': len(sent_ids), 'failed': failed}

    def heartbeat(self) -> dict[str, Any]:
        status = self.sender(
            'GET', self.remote_url + '/api/trevor/status', None, self._headers()
        )
        replay = self.flush()
        return {'ok': bool(status.get('ok', False)), 'remote': status, 'replay': replay}


__all__ = ['EncryptedOfflineQueue', 'TrevorEdgeClient']

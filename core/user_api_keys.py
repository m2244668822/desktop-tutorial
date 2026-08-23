from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


VALID_SCOPES = frozenset({'chat', 'memory', 'tasks', 'git', 'users', 'audit'})


class TrevorAPIKeyStore:
    def __init__(
        self,
        path: str | Path,
        *,
        hmac_secret: bytes | str,
        now: Callable[[], datetime] | None = None,
    ):
        self.path = Path(path)
        self.hmac_secret = (
            hmac_secret.encode('utf-8') if isinstance(hmac_secret, str) else bytes(hmac_secret)
        )
        if len(self.hmac_secret) < 32:
            raise ValueError('hmac_secret_too_short')
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {'schema_version': 1, 'keys': []}
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            raise RuntimeError('api_key_store_invalid')
        if not isinstance(payload, dict) or not isinstance(payload.get('keys', []), list):
            raise RuntimeError('api_key_store_invalid')
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_name(f'.{self.path.name}.tmp-{os.getpid()}')
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def _digest(self, api_key: str) -> str:
        return hmac.new(
            self.hmac_secret,
            str(api_key or '').encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.items()
            if key not in {'digest'}
        }

    @staticmethod
    def _normalize_scopes(scopes: Iterable[str]) -> list[str]:
        normalized = sorted({str(scope or '').strip().lower() for scope in scopes})
        if not normalized or any(scope not in VALID_SCOPES for scope in normalized):
            raise ValueError('invalid_scope')
        return normalized

    def create(self, label: str, scopes: Iterable[str]) -> dict[str, Any]:
        normalized_scopes = self._normalize_scopes(scopes)
        api_key = f'trv_{secrets.token_urlsafe(32)}'
        record = {
            'id': str(uuid.uuid4()),
            'label': str(label or 'unnamed').strip()[:120] or 'unnamed',
            'prefix': api_key[:12],
            'digest': self._digest(api_key),
            'scopes': normalized_scopes,
            'status': 'active',
            'created_at': self.now().astimezone(timezone.utc).isoformat(),
            'revoked_at': '',
        }
        with self._lock:
            payload = self._load()
            payload.setdefault('keys', []).append(record)
            payload['updated_at'] = self.now().astimezone(timezone.utc).isoformat()
            self._write(payload)
        return {'api_key': api_key, 'record': self._public(record)}

    def authenticate(self, api_key: str, *, required_scope: str) -> dict[str, Any]:
        scope = str(required_scope or '').strip().lower()
        if scope not in VALID_SCOPES:
            return {'ok': False, 'error': 'invalid_scope'}
        supplied = str(api_key or '').strip()
        if not supplied.startswith('trv_'):
            return {'ok': False, 'error': 'invalid_key'}
        supplied_digest = self._digest(supplied)
        payload = self._load()
        matching: dict[str, Any] | None = None
        for record in payload.get('keys', []):
            if not isinstance(record, dict) or record.get('prefix') != supplied[:12]:
                continue
            if hmac.compare_digest(str(record.get('digest', '')), supplied_digest):
                matching = record
                break
        if matching is None:
            return {'ok': False, 'error': 'invalid_key'}
        if matching.get('status') != 'active':
            return {'ok': False, 'error': 'key_revoked'}
        if scope not in set(matching.get('scopes', [])):
            return {'ok': False, 'error': 'scope_denied'}
        return {
            'ok': True,
            'key_id': matching.get('id', ''),
            'prefix': matching.get('prefix', ''),
            'scopes': list(matching.get('scopes', [])),
        }

    def revoke(self, key_id: str) -> bool:
        target = str(key_id or '').strip()
        with self._lock:
            payload = self._load()
            changed = False
            for record in payload.get('keys', []):
                if isinstance(record, dict) and record.get('id') == target:
                    record['status'] = 'revoked'
                    record['revoked_at'] = self.now().astimezone(timezone.utc).isoformat()
                    changed = True
                    break
            if changed:
                payload['updated_at'] = self.now().astimezone(timezone.utc).isoformat()
                self._write(payload)
            return changed

    def list_public(self) -> list[dict[str, Any]]:
        return [
            self._public(record)
            for record in self._load().get('keys', [])
            if isinstance(record, dict)
        ]


__all__ = ['TrevorAPIKeyStore', 'VALID_SCOPES']

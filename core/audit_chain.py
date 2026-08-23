from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from core.content_sanitizer import ExternalContentSanitizer


GENESIS_HASH = '0' * 64


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


class HashChainAuditLog:
    def __init__(
        self,
        path: str | Path,
        *,
        sanitizer: ExternalContentSanitizer | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.path = Path(path)
        self.sanitizer = sanitizer or ExternalContentSanitizer()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    def _sanitize(self, value: Any, depth: int = 0) -> Any:
        if depth > 12:
            return '[TRUNCATED_DEPTH]'
        if isinstance(value, dict):
            return {
                str(key)[:160]: self._sanitize(item, depth + 1)
                for key, item in list(value.items())[:1000]
            }
        if isinstance(value, (list, tuple)):
            return [self._sanitize(item, depth + 1) for item in list(value)[:1000]]
        if isinstance(value, str):
            return self.sanitizer.sanitize(message=value[:100000]).payload['message']
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return self.sanitizer.sanitize(message=str(value)[:100000]).payload['message']

    @staticmethod
    def _lock_file(file_handle: Any) -> None:
        try:
            import fcntl
        except ImportError:
            return
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _unlock_file(file_handle: Any) -> None:
        try:
            import fcntl
        except ImportError:
            return
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _verify_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
        previous_hash = GENESIS_HASH
        count = 0
        for index, event in enumerate(events, start=1):
            if event.get('previous_hash') != previous_hash:
                return {'ok': False, 'events': count, 'invalid_line': index}
            claimed_hash = str(event.get('event_hash', '') or '')
            unsigned = dict(event)
            unsigned.pop('event_hash', None)
            expected_hash = hashlib.sha256(_canonical(unsigned)).hexdigest()
            if not claimed_hash or claimed_hash != expected_hash:
                return {'ok': False, 'events': count, 'invalid_line': index}
            previous_hash = claimed_hash
            count += 1
        return {'ok': True, 'events': count, 'last_hash': previous_hash}

    @staticmethod
    def _parse_lines(lines: Iterable[str]) -> tuple[list[dict[str, Any]], int | None]:
        events: list[dict[str, Any]] = []
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return events, index
            if not isinstance(event, dict):
                return events, index
            events.append(event)
        return events, None

    def verify(self) -> dict[str, Any]:
        if not self.path.exists():
            return {'ok': True, 'events': 0, 'last_hash': GENESIS_HASH}
        try:
            lines = self.path.read_text(encoding='utf-8').splitlines()
        except OSError:
            return {'ok': False, 'events': 0, 'error': 'audit_read_failed'}
        events, invalid_line = self._parse_lines(lines)
        if invalid_line is not None:
            return {'ok': False, 'events': len(events), 'invalid_line': invalid_line}
        return self._verify_events(events)

    def append(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str = 'trevor',
    ) -> dict[str, Any]:
        event_name = str(event_type or '').strip().lower()
        if not event_name:
            raise ValueError('event_type_required')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        with self._lock, self.path.open('a+', encoding='utf-8') as file_handle:
            os.chmod(self.path, 0o600)
            self._lock_file(file_handle)
            try:
                file_handle.seek(0)
                events, invalid_line = self._parse_lines(file_handle.readlines())
                verification = (
                    {'ok': False, 'invalid_line': invalid_line}
                    if invalid_line is not None
                    else self._verify_events(events)
                )
                if not verification.get('ok'):
                    raise RuntimeError('audit_chain_invalid')
                event = {
                    'schema_version': 1,
                    'event_id': str(uuid.uuid4()),
                    'created_at': self.now().astimezone(timezone.utc).isoformat(),
                    'event_type': event_name,
                    'actor': str(actor or 'trevor')[:120],
                    'payload': self._sanitize(payload or {}),
                    'previous_hash': verification.get('last_hash', GENESIS_HASH),
                }
                event['event_hash'] = hashlib.sha256(_canonical(event)).hexdigest()
                file_handle.seek(0, os.SEEK_END)
                file_handle.write(_canonical(event).decode('utf-8') + '\n')
                file_handle.flush()
                os.fsync(file_handle.fileno())
                return event
            finally:
                self._unlock_file(file_handle)

    def read(self, *, limit: int = 100) -> list[dict[str, Any]]:
        verification = self.verify()
        if not verification.get('ok'):
            raise RuntimeError('audit_chain_invalid')
        if not self.path.exists():
            return []
        events, _ = self._parse_lines(self.path.read_text(encoding='utf-8').splitlines())
        return events[-max(1, min(int(limit), 1000)) :]


__all__ = ['GENESIS_HASH', 'HashChainAuditLog']

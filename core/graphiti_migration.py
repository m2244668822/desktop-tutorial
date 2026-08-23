from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from core.audit_chain import HashChainAuditLog
from core.content_sanitizer import ExternalContentSanitizer


def _content_hash(user: Any, assistant: Any) -> str:
    normalized = '\n'.join(
        ' '.join(str(value or '').split()).strip().lower()
        for value in (user, assistant)
    )
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.tmp-{os.getpid()}')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


class GraphitiMigrationRunner:
    def __init__(
        self,
        manifest_path: str | Path,
        *,
        sender: Callable[[dict[str, Any]], Any],
        sanitizer: ExternalContentSanitizer | None = None,
        audit_log: HashChainAuditLog | None = None,
    ):
        self.manifest_path = Path(manifest_path)
        self.sender = sender
        self.sanitizer = sanitizer or ExternalContentSanitizer()
        self.audit_log = audit_log

    def run(self, conversations: Mapping[str, Any]) -> dict[str, Any]:
        previous = _read_manifest(self.manifest_path)
        migrated_hashes = set(previous.get('content_hashes', []) or [])
        seen_this_run: set[str] = set()
        migrated = 0
        skipped = 0
        failed = 0
        for thread_id, thread in conversations.items():
            if not isinstance(thread, Mapping):
                continue
            for index, message in enumerate(thread.get('messages', []) or []):
                if not isinstance(message, Mapping):
                    continue
                content_hash = str(
                    (message.get('metadata') or {}).get('content_hash', '') or ''
                ) or _content_hash(message.get('user'), message.get('assistant'))
                if content_hash in migrated_hashes or content_hash in seen_this_run:
                    skipped += 1
                    continue
                seen_this_run.add(content_hash)
                metadata = dict(message.get('metadata') or {})
                source_role = str(metadata.get('source_role', '崔佛') or '崔佛')
                capability_mode = str(metadata.get('capability_mode', 'general') or 'general')
                body = (
                    f"User: {str(message.get('user', '') or '').strip()}\n"
                    f"Trevor: {str(message.get('assistant', '') or '').strip()}"
                )
                sanitized = self.sanitizer.sanitize(message=body)
                timestamp = str(
                    message.get('timestamp', thread.get('created_at', '')) or ''
                )
                if not timestamp:
                    timestamp = datetime.now(timezone.utc).isoformat()
                payload = {
                    'name': f'trevor-{content_hash[:16]}',
                    'episode_body': sanitized.payload['message'],
                    'source_description': f'trevor_memory:{source_role}',
                    'reference_time': timestamp,
                    'episode_uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, f'trevor:{content_hash}')),
                    'group_id': 'trevor',
                    'metadata': {
                        'source_role': source_role,
                        'capability_mode': capability_mode,
                        'thread_id': str(thread_id),
                        'turn_index': index,
                        'redaction_count': sanitized.redaction_count,
                    },
                }
                try:
                    self.sender(payload)
                except Exception:
                    failed += 1
                    continue
                migrated_hashes.add(content_hash)
                migrated += 1
        manifest = {
            'schema_version': 1,
            'graphiti_version': '0.29.3',
            'identity': 'trevor',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'migrated_count': len(migrated_hashes),
            'content_hashes': sorted(migrated_hashes),
            'deduplication': 'sha256_normalized_turn',
            'redacted_before_upload': True,
            'rerunnable': True,
        }
        _atomic_manifest(self.manifest_path, manifest)
        result = {
            'ok': failed == 0,
            'migrated': migrated,
            'skipped': skipped,
            'failed': failed,
            'total_migrated': len(migrated_hashes),
            'manifest': str(self.manifest_path),
        }
        if self.audit_log is not None:
            self.audit_log.append(
                'data_migration_completed',
                {
                    'target': 'graphiti',
                    'ok': result['ok'],
                    'migrated': migrated,
                    'skipped': skipped,
                    'failed': failed,
                    'total_migrated': len(migrated_hashes),
                    'redacted_before_upload': True,
                    'rerunnable': True,
                },
            )
        return result


__all__ = ['GraphitiMigrationRunner']

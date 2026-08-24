from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from core.audit_chain import HashChainAuditLog
from core.content_sanitizer import ExternalContentSanitizer


DEFAULT_BATCH_TURNS = 24
DEFAULT_BATCH_BYTES = 40_000
DEFAULT_UPLOAD_BATCH_TURNS = 8
DEFAULT_UPLOAD_BATCH_BYTES = 14_000
MAX_EPISODE_BYTES = 49_000


@dataclass(frozen=True)
class _MigrationTurn:
    content_hash: str
    timestamp: str
    thread_ref: str
    turn_index: int
    source_role: str
    capability_mode: str
    body: str
    redaction_count: int


@dataclass(frozen=True)
class _UploadRecord:
    logical_batch_hash: str
    upload_batch_hash: str
    strategy: str
    content_hashes: tuple[str, ...]


def _content_hash(user: Any, assistant: Any) -> str:
    normalized = '\n'.join(
        ' '.join(str(value or '').split()).strip().lower()
        for value in (user, assistant)
    )
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _valid_content_hash(value: Any) -> str:
    candidate = str(value or '').strip().lower()
    if len(candidate) == 64 and all(
        character in '0123456789abcdef' for character in candidate
    ):
        return candidate
    return ''


def _timestamp(value: Any) -> str:
    candidate = str(value or '').strip()
    if not candidate:
        return '1970-01-01T00:00:00+00:00'
    try:
        parsed = datetime.fromisoformat(candidate.replace('Z', '+00:00'))
    except ValueError:
        return '1970-01-01T00:00:00+00:00'
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _safe_label(value: Any, fallback: str, limit: int) -> str:
    normalized = ' '.join(str(value or '').split()).strip()
    return (normalized or fallback)[:limit]


def _turn_frame(turn: _MigrationTurn) -> str:
    return (
        '[Trevor memory turn]\n'
        f'Timestamp: {turn.timestamp}\n'
        f'Thread ref: {turn.thread_ref}\n'
        f'Source role: {turn.source_role}\n'
        f'Capability: {turn.capability_mode}\n'
        f'{turn.body}'
    )


def _build_batches(
    turns: list[_MigrationTurn],
    *,
    max_batch_turns: int,
    max_batch_bytes: int,
) -> list[list[_MigrationTurn]]:
    batches: list[list[_MigrationTurn]] = []
    current: list[_MigrationTurn] = []
    current_bytes = 0
    delimiter_bytes = len('\n\n---\n\n'.encode('utf-8'))
    for turn in turns:
        turn_bytes = len(_turn_frame(turn).encode('utf-8'))
        additional_bytes = turn_bytes + (delimiter_bytes if current else 0)
        if current and (
            len(current) >= max_batch_turns
            or current_bytes + additional_bytes > max_batch_bytes
        ):
            batches.append(current)
            current = []
            current_bytes = 0
            additional_bytes = turn_bytes
        current.append(turn)
        current_bytes += additional_bytes
    if current:
        batches.append(current)
    return batches


def _batch_hash(turns: list[_MigrationTurn]) -> str:
    return hashlib.sha256(
        '\n'.join(turn.content_hash for turn in turns).encode('ascii')
    ).hexdigest()


def _payload_for_batch(batch: list[_MigrationTurn]) -> tuple[str, dict[str, Any]]:
    body = '\n\n---\n\n'.join(_turn_frame(turn) for turn in batch)
    batch_hash = _batch_hash(batch)
    source_roles = {turn.source_role for turn in batch}
    capability_modes = {turn.capability_mode for turn in batch}
    return batch_hash, {
        'name': f'trevor-batch-{batch_hash[:24]}',
        'episode_body': body,
        'source_description': 'trevor_memory:unified_batch',
        'reference_time': batch[-1].timestamp,
        'episode_uuid': str(
            uuid.uuid5(uuid.NAMESPACE_URL, f'trevor:batch:{batch_hash}')
        ),
        'group_id': 'trevor',
        'metadata': {
            'source_role': (
                next(iter(source_roles)) if len(source_roles) == 1 else 'mixed'
            ),
            'capability_mode': (
                next(iter(capability_modes))
                if len(capability_modes) == 1
                else 'mixed'
            ),
            'turn_count': len(batch),
            'thread_count': len({turn.thread_ref for turn in batch}),
            'redaction_count': sum(turn.redaction_count for turn in batch),
        },
    }


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


def _checkpoint_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(f'{manifest_path.suffix}.checkpoint')


def _upload_journal_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(f'{manifest_path.suffix}.uploads')


def _read_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        lines = path.read_text(encoding='ascii').splitlines()
    except OSError as exc:
        raise RuntimeError('graphiti_checkpoint_unreadable') from exc
    hashes: set[str] = set()
    for line in lines:
        value = line.strip().lower()
        if len(value) != 64 or any(character not in '0123456789abcdef' for character in value):
            raise RuntimeError('graphiti_checkpoint_invalid')
        hashes.add(value)
    return hashes


def _append_checkpoint(path: Path, content_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError('graphiti_checkpoint_unwritable') from exc
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, f'{content_hash}\n'.encode('ascii'))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _repair_upload_journal(path: Path, lines: list[str]) -> None:
    temporary = path.with_name(f'{path.name}.repair-{os.getpid()}')
    payload = '\n'.join(lines)
    if payload:
        payload += '\n'
    try:
        temporary.write_text(payload, encoding='ascii')
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        raise RuntimeError('graphiti_upload_journal_unwritable') from exc
    finally:
        temporary.unlink(missing_ok=True)


def _read_upload_journal(path: Path) -> list[_UploadRecord]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding='ascii')
    except OSError as exc:
        raise RuntimeError('graphiti_upload_journal_unreadable') from exc
    lines = raw.splitlines()
    records: list[_UploadRecord] = []
    valid_lines: list[str] = []
    for index, line in enumerate(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1 and not raw.endswith('\n'):
                break
            raise RuntimeError('graphiti_upload_journal_invalid') from exc
        if not isinstance(payload, Mapping) or payload.get('schema_version') != 1:
            raise RuntimeError('graphiti_upload_journal_invalid')
        logical_batch_hash = _valid_content_hash(payload.get('logical_batch_hash'))
        upload_batch_hash = _valid_content_hash(payload.get('upload_batch_hash'))
        strategy = str(payload.get('strategy', '') or '')
        raw_hashes = payload.get('content_hashes')
        if (
            not logical_batch_hash
            or not upload_batch_hash
            or strategy
            not in {
                'deterministic_pending_sub_batch_v2',
                'deterministic_sub_batch_v2',
                'logical_batch_v1',
            }
            or not isinstance(raw_hashes, list)
            or not raw_hashes
        ):
            raise RuntimeError('graphiti_upload_journal_invalid')
        content_hashes = tuple(_valid_content_hash(value) for value in raw_hashes)
        if any(not value for value in content_hashes) or len(set(content_hashes)) != len(
            content_hashes
        ):
            raise RuntimeError('graphiti_upload_journal_invalid')
        expected_upload_hash = hashlib.sha256(
            '\n'.join(content_hashes).encode('ascii')
        ).hexdigest()
        if upload_batch_hash != expected_upload_hash:
            raise RuntimeError('graphiti_upload_journal_invalid')
        records.append(
            _UploadRecord(
                logical_batch_hash=logical_batch_hash,
                upload_batch_hash=upload_batch_hash,
                strategy=strategy,
                content_hashes=content_hashes,
            )
        )
        valid_lines.append(line)
    if raw and not raw.endswith('\n'):
        _repair_upload_journal(path, valid_lines)
    return records


def _append_upload_journal(
    path: Path,
    *,
    logical_batch_hash: str,
    upload_batch_hash: str,
    strategy: str,
    content_hashes: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        serialized = json.dumps(
            {
                'schema_version': 1,
                'logical_batch_hash': logical_batch_hash,
                'upload_batch_hash': upload_batch_hash,
                'strategy': strategy,
                'content_hashes': list(content_hashes),
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode('ascii') + b'\n'
        offset = 0
        while offset < len(serialized):
            written = os.write(descriptor, serialized[offset:])
            if written <= 0:
                raise OSError('short write')
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise RuntimeError('graphiti_upload_journal_unwritable') from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


class GraphitiMigrationRunner:
    def __init__(
        self,
        manifest_path: str | Path,
        *,
        sender: Callable[[dict[str, Any]], Any],
        sanitizer: ExternalContentSanitizer | None = None,
        audit_log: HashChainAuditLog | None = None,
        max_batch_turns: int = DEFAULT_BATCH_TURNS,
        max_batch_bytes: int = DEFAULT_BATCH_BYTES,
        max_upload_turns: int = DEFAULT_UPLOAD_BATCH_TURNS,
        max_upload_bytes: int = DEFAULT_UPLOAD_BATCH_BYTES,
    ):
        self.manifest_path = Path(manifest_path)
        self.sender = sender
        self.sanitizer = sanitizer or ExternalContentSanitizer()
        self.audit_log = audit_log
        self.max_batch_turns = max(1, min(100, int(max_batch_turns)))
        self.max_batch_bytes = max(
            1_000, min(MAX_EPISODE_BYTES, int(max_batch_bytes))
        )
        self.max_upload_turns = max(1, min(100, int(max_upload_turns)))
        self.max_upload_bytes = max(
            1_000, min(MAX_EPISODE_BYTES, int(max_upload_bytes))
        )

    def run(self, conversations: Mapping[str, Any]) -> dict[str, Any]:
        previous = _read_manifest(self.manifest_path)
        previous_completed = previous.get('completed') is True
        checkpoint = _checkpoint_path(self.manifest_path)
        upload_journal = _upload_journal_path(self.manifest_path)
        upload_records = _read_upload_journal(upload_journal)
        migrated_hashes = set(previous.get('content_hashes', []) or [])
        migrated_hashes.update(_read_checkpoint(checkpoint))
        seen_this_run: set[str] = set()
        source_hashes: set[str] = set()
        turns: list[_MigrationTurn] = []
        migrated = 0
        skipped = 0
        failed = 0
        for thread_id, thread in conversations.items():
            if not isinstance(thread, Mapping):
                continue
            for index, message in enumerate(thread.get('messages', []) or []):
                if not isinstance(message, Mapping):
                    continue
                raw_metadata = message.get('metadata')
                metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
                content_hash = _valid_content_hash(metadata.get('content_hash')) or _content_hash(
                    message.get('user'), message.get('assistant')
                )
                source_hashes.add(content_hash)
                if content_hash in seen_this_run:
                    skipped += 1
                    continue
                seen_this_run.add(content_hash)
                source_role = _safe_label(metadata.get('source_role'), '崔佛', 80)
                capability_mode = _safe_label(
                    metadata.get('capability_mode'), 'general', 40
                )
                body = (
                    f"User: {str(message.get('user', '') or '').strip()}\n"
                    f"Trevor: {str(message.get('assistant', '') or '').strip()}"
                )
                sanitized = self.sanitizer.sanitize(message=body)
                timestamp = _timestamp(
                    message.get('timestamp', thread.get('created_at', ''))
                )
                thread_ref = hashlib.sha256(
                    str(thread_id).encode('utf-8')
                ).hexdigest()[:16]
                turns.append(
                    _MigrationTurn(
                        content_hash=content_hash,
                        timestamp=timestamp,
                        thread_ref=thread_ref,
                        turn_index=index,
                        source_role=source_role,
                        capability_mode=capability_mode,
                        body=sanitized.payload['message'],
                        redaction_count=sanitized.redaction_count,
                    )
                )

        turns.sort(
            key=lambda turn: (
                turn.timestamp,
                turn.thread_ref,
                turn.turn_index,
                turn.content_hash,
            )
        )
        batches = _build_batches(
            turns,
            max_batch_turns=self.max_batch_turns,
            max_batch_bytes=self.max_batch_bytes,
        )
        logical_batches = {_batch_hash(batch): batch for batch in batches}
        previous_batching = previous.get('batching')
        previous_subbatched = (
            previous_batching.get('subbatched_logical_hashes', [])
            if isinstance(previous_batching, Mapping)
            else []
        )
        subbatched_logical_hashes = {
            value
            for item in previous_subbatched
            if (value := _valid_content_hash(item)) in logical_batches
        }
        previous_pending_only = (
            previous_batching.get('pending_only_logical_hashes', [])
            if isinstance(previous_batching, Mapping)
            else []
        )
        pending_only_logical_hashes = {
            value
            for item in previous_pending_only
            if (value := _valid_content_hash(item)) in logical_batches
        }
        for record in upload_records:
            logical_batch = logical_batches.get(record.logical_batch_hash)
            if logical_batch is None:
                continue
            logical_content_hashes = {
                turn.content_hash for turn in logical_batch
            }
            if not set(record.content_hashes).issubset(logical_content_hashes):
                raise RuntimeError('graphiti_upload_journal_invalid')
            if record.strategy == 'deterministic_sub_batch_v2':
                subbatched_logical_hashes.add(record.logical_batch_hash)
            if record.strategy == 'deterministic_pending_sub_batch_v2':
                subbatched_logical_hashes.add(record.logical_batch_hash)
                pending_only_logical_hashes.add(record.logical_batch_hash)
            for content_hash in record.content_hashes:
                if content_hash in migrated_hashes:
                    continue
                _append_checkpoint(checkpoint, content_hash)
                migrated_hashes.add(content_hash)
        completed_batches = 0
        upload_batch_count = 0
        for batch in batches:
            logical_batch_hash = _batch_hash(batch)
            pending = [
                turn for turn in batch if turn.content_hash not in migrated_hashes
            ]
            skipped += len(batch) - len(pending)
            if not pending:
                continue
            use_pending_only = (
                previous_completed
                or logical_batch_hash in pending_only_logical_hashes
            )
            use_safe_sub_batches = (
                logical_batch_hash in subbatched_logical_hashes
                or len(pending) == len(batch)
                or use_pending_only
            )
            if use_safe_sub_batches:
                upload_batches = _build_batches(
                    pending if use_pending_only else batch,
                    max_batch_turns=self.max_upload_turns,
                    max_batch_bytes=self.max_upload_bytes,
                )
                upload_strategy = (
                    'deterministic_pending_sub_batch_v2'
                    if use_pending_only
                    else 'deterministic_sub_batch_v2'
                )
                subbatched_logical_hashes.add(logical_batch_hash)
                if use_pending_only:
                    pending_only_logical_hashes.add(logical_batch_hash)
            else:
                upload_batches = [batch]
                upload_strategy = 'logical_batch_v1'
            for upload_batch in upload_batches:
                upload_pending = [
                    turn
                    for turn in upload_batch
                    if turn.content_hash not in migrated_hashes
                ]
                if not upload_pending:
                    continue
                upload_batch_count += 1
                upload_batch_hash, payload = _payload_for_batch(upload_batch)
                if len(payload['episode_body'].encode('utf-8')) > MAX_EPISODE_BYTES:
                    failed += len(upload_pending)
                    continue
                try:
                    self.sender(payload)
                except Exception:
                    failed += len(upload_pending)
                    continue
                _append_upload_journal(
                    upload_journal,
                    logical_batch_hash=logical_batch_hash,
                    upload_batch_hash=upload_batch_hash,
                    strategy=upload_strategy,
                    content_hashes=tuple(
                        turn.content_hash for turn in upload_batch
                    ),
                )
                for turn in upload_batch:
                    if turn.content_hash in migrated_hashes:
                        continue
                    _append_checkpoint(checkpoint, turn.content_hash)
                    migrated_hashes.add(turn.content_hash)
                    migrated += 1
                completed_batches += 1
        completed = failed == 0 and source_hashes.issubset(migrated_hashes)
        manifest = {
            'schema_version': 3,
            'graphiti_version': '0.29.3',
            'identity': 'trevor',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'migrated_count': len(migrated_hashes),
            'source_count': len(source_hashes),
            'failed_count': failed,
            'completed': completed,
            'status': 'completed' if completed else 'incomplete',
            'content_hashes': sorted(migrated_hashes),
            'deduplication': 'sha256_normalized_turn',
            'redacted_before_upload': True,
            'rerunnable': True,
            'batching': {
                'strategy': 'chronological_logical_window_with_sub_batches_v2',
                'max_turns': self.max_batch_turns,
                'max_utf8_bytes': self.max_batch_bytes,
                'batch_count': len(batches),
                'upload_max_turns': self.max_upload_turns,
                'upload_max_utf8_bytes': self.max_upload_bytes,
                'subbatched_logical_hashes': sorted(subbatched_logical_hashes),
                'pending_only_logical_hashes': sorted(
                    pending_only_logical_hashes
                ),
            },
        }
        _atomic_manifest(self.manifest_path, manifest)
        if completed:
            checkpoint.unlink(missing_ok=True)
            upload_journal.unlink(missing_ok=True)
        result = {
            'ok': completed,
            'completed': completed,
            'migrated': migrated,
            'skipped': skipped,
            'failed': failed,
            'batches': completed_batches,
            'batch_count': len(batches),
            'upload_batch_count': upload_batch_count,
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
                    'batches': completed_batches,
                    'batch_count': len(batches),
                    'upload_batch_count': upload_batch_count,
                    'total_migrated': len(migrated_hashes),
                    'source_count': len(source_hashes),
                    'completed': completed,
                    'redacted_before_upload': True,
                    'rerunnable': True,
                },
            )
        return result


__all__ = [
    'DEFAULT_UPLOAD_BATCH_BYTES',
    'DEFAULT_UPLOAD_BATCH_TURNS',
    'GraphitiMigrationRunner',
]

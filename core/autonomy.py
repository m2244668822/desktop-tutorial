from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from core.trevor_identity import TREVOR_AGENT_ID, TREVOR_DISPLAY_NAME

try:
    import fcntl
except ImportError:
    fcntl = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or '').replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}-{threading.get_ident()}')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


@contextmanager
def _exclusive_file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@dataclass(frozen=True)
class AutonomyConfig:
    heartbeat_seconds: int = 60
    evaluation_seconds: int = 900
    max_concurrent_tasks: int = 1
    user_active_window_seconds: int = 300
    cpu_pause_percent: float = 80.0
    memory_pause_percent: float = 85.0
    lease_ttl_seconds: int = 1800
    nightly_maintenance_hour: int = 3


class AutonomyLease:
    def __init__(
        self,
        path: str | Path,
        *,
        ttl_seconds: int = 1800,
        now: Callable[[], datetime] = _utc_now,
    ):
        self.path = Path(path)
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.now = now

    def _existing(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def acquire(self, owner: str) -> bool:
        owner_id = str(owner or '').strip()
        if not owner_id:
            raise ValueError('lease_owner_required')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        for _ in range(2):
            now = self.now().astimezone(timezone.utc)
            payload = {
                'owner': owner_id,
                'lease_id': secrets.token_hex(16),
                'acquired_at': now.isoformat(),
                'expires_at': (now + timedelta(seconds=self.ttl_seconds)).isoformat(),
            }
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                existing = self._existing()
                expires_at = _parse_datetime(existing.get('expires_at'))
                if expires_at is not None and expires_at > now:
                    return False
                try:
                    self.path.unlink()
                except OSError:
                    return False
                continue
            try:
                os.write(
                    descriptor,
                    (json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8'),
                )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return True
        return False

    def release(self, owner: str) -> bool:
        existing = self._existing()
        if existing.get('owner') != str(owner or '').strip():
            return False
        try:
            self.path.unlink()
        except OSError:
            return False
        return True


class AutonomyPolicy:
    ALLOWED_CATEGORIES = frozenset(
        {'bugfix', 'test', 'refactor', 'content', 'small_feature', 'maintenance'}
    )
    FORBIDDEN_MARKERS = (
        '購買',
        '付款',
        '刷卡',
        '變更帳戶',
        '修改帳戶',
        '寄信',
        '發信',
        '對外通訊',
        '刪除資料',
        '清空資料',
        'drop database',
        'delete production',
        'purchase',
        'payment',
        'change account',
        'send email',
        'external communication',
    )

    def __init__(self, config: AutonomyConfig | None = None):
        self.config = config or AutonomyConfig()

    def evaluate(self, task: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
        category = str(task.get('category', 'maintenance') or 'maintenance').strip().lower()
        instruction = str(task.get('input', '') or '').strip().lower()
        if category not in self.ALLOWED_CATEGORIES:
            return {'allowed': False, 'reason': 'category_not_allowed'}
        if any(marker in instruction for marker in self.FORBIDDEN_MARKERS):
            return {'allowed': False, 'reason': 'forbidden_action'}
        if bool(signals.get('user_active', False)):
            return {'allowed': False, 'reason': 'user_active'}
        if float(signals.get('cpu_percent', 0) or 0) >= self.config.cpu_pause_percent:
            return {'allowed': False, 'reason': 'high_cpu'}
        if float(signals.get('memory_percent', 0) or 0) >= self.config.memory_pause_percent:
            return {'allowed': False, 'reason': 'high_memory'}
        if not bool(signals.get('quota_sufficient', True)):
            return {'allowed': False, 'reason': 'quota_insufficient'}
        if not bool(signals.get('services_healthy', True)):
            return {'allowed': False, 'reason': 'service_unhealthy'}
        return {'allowed': True, 'reason': 'approved'}


class AutonomyQueue:
    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = _utc_now,
        claim_ttl_seconds: int = 1800,
    ):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(f'{self.path.suffix}.lock')
        self.now = now
        self.claim_ttl_seconds = max(60, int(claim_ttl_seconds))
        self._lock = threading.Lock()

    @contextmanager
    def _mutation_lock(self):
        with self._lock:
            with _exclusive_file_lock(self.lock_path):
                yield

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {'schema_version': 1, 'tasks': []}
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            raise RuntimeError('autonomy_queue_invalid')
        if not isinstance(payload, dict) or not isinstance(payload.get('tasks', []), list):
            raise RuntimeError('autonomy_queue_invalid')
        return payload

    def enqueue(
        self,
        instruction: str,
        *,
        capability_mode: str = 'general',
        category: str = 'maintenance',
        priority: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self.now().astimezone(timezone.utc).isoformat()
        task = {
            'id': f'trevor-{uuid.uuid4()}',
            'agent': TREVOR_AGENT_ID,
            'role': TREVOR_DISPLAY_NAME,
            'capability_mode': str(capability_mode or 'general').strip().lower(),
            'category': str(category or 'maintenance').strip().lower(),
            'input': str(instruction or '').strip(),
            'priority': max(0, min(100, int(priority))),
            'status': 'pending',
            'created_at': now,
            'updated_at': now,
            'metadata': dict(metadata or {}),
        }
        if not task['input']:
            raise ValueError('task_input_required')
        with self._mutation_lock():
            payload = self._load()
            payload.setdefault('tasks', []).append(task)
            payload['tasks'].sort(
                key=lambda item: (int(item.get('priority', 5)), str(item.get('created_at', '')))
            )
            payload['updated_at'] = now
            _atomic_json(self.path, payload)
        return dict(task)

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        worker = str(worker_id or '').strip()
        if not worker:
            raise ValueError('worker_id_required')
        with self._mutation_lock():
            payload = self._load()
            tasks = payload.get('tasks', [])
            now = self.now().astimezone(timezone.utc)
            for task in tasks:
                if not isinstance(task, dict) or task.get('status') != 'running':
                    continue
                expires_at = _parse_datetime(task.get('lease_expires_at'))
                if expires_at is None:
                    updated_at = _parse_datetime(task.get('updated_at'))
                    expires_at = (
                        updated_at + timedelta(seconds=self.claim_ttl_seconds)
                        if updated_at is not None
                        else now
                    )
                if expires_at > now:
                    continue
                task['status'] = 'pending'
                task.pop('worker_id', None)
                task.pop('lease_expires_at', None)
                task['pause_reason'] = 'stale_worker_reclaimed'
                task['reclaimed_at'] = now.isoformat()
                task['updated_at'] = now.isoformat()
            if any(
                isinstance(task, dict) and task.get('status') == 'running'
                for task in tasks
            ):
                return None
            pending = next(
                (
                    task
                    for task in tasks
                    if isinstance(task, dict) and task.get('status') == 'pending'
                ),
                None,
            )
            if pending is None:
                return None
            pending['status'] = 'running'
            pending['worker_id'] = worker
            pending['updated_at'] = now.isoformat()
            pending['lease_expires_at'] = (
                now + timedelta(seconds=self.claim_ttl_seconds)
            ).isoformat()
            payload['updated_at'] = pending['updated_at']
            _atomic_json(self.path, payload)
            return dict(pending)

    def finish(
        self,
        task_id: str,
        *,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str = '',
    ) -> bool:
        target = str(task_id or '').strip()
        with self._mutation_lock():
            payload = self._load()
            for task in payload.get('tasks', []):
                if not isinstance(task, dict) or task.get('id') != target:
                    continue
                task['status'] = 'completed' if success else 'failed'
                task['result'] = dict(result or {})
                task['error'] = str(error or '')[:1000]
                task.pop('worker_id', None)
                task.pop('lease_expires_at', None)
                task['updated_at'] = self.now().astimezone(timezone.utc).isoformat()
                payload['updated_at'] = task['updated_at']
                _atomic_json(self.path, payload)
                return True
        return False

    def defer(self, task_id: str, *, reason: str) -> bool:
        target = str(task_id or '').strip()
        with self._mutation_lock():
            payload = self._load()
            for task in payload.get('tasks', []):
                if not isinstance(task, dict) or task.get('id') != target:
                    continue
                task['status'] = 'pending'
                task.pop('worker_id', None)
                task.pop('lease_expires_at', None)
                task['pause_reason'] = str(reason or 'paused')[:200]
                task['updated_at'] = self.now().astimezone(timezone.utc).isoformat()
                payload['updated_at'] = task['updated_at']
                _atomic_json(self.path, payload)
                return True
        return False

    def tasks(self) -> list[dict[str, Any]]:
        with self._mutation_lock():
            return [
                dict(task)
                for task in self._load().get('tasks', [])
                if isinstance(task, dict)
            ]


def mark_user_activity(data_root: str | Path) -> Path:
    path = Path(data_root) / 'activity' / 'last_user_activity'
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.touch()
    os.chmod(path, 0o600)
    return path


def user_is_active(data_root: str | Path, *, window_seconds: int = 300) -> bool:
    path = Path(data_root) / 'activity' / 'last_user_activity'
    try:
        age = _utc_now().timestamp() - path.stat().st_mtime
    except OSError:
        return False
    return age <= max(1, int(window_seconds))


__all__ = [
    'AutonomyConfig',
    'AutonomyLease',
    'AutonomyPolicy',
    'AutonomyQueue',
    'mark_user_activity',
    'user_is_active',
]

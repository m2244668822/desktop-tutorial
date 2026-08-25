#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audit_chain import HashChainAuditLog
from core.autonomy import AutonomyConfig, AutonomyQueue, user_is_active
from core.autonomy_runner import AutonomyRunner
from core.data_paths import resolve_data_root


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def provider_signals(public_status: dict[str, Any]) -> dict[str, bool]:
    providers = public_status.get('providers', []) if isinstance(public_status, dict) else []
    nvidia = next(
        (
            item
            for item in providers
            if isinstance(item, dict) and item.get('provider') == 'nvidia'
        ),
        {},
    )
    reason = str(nvidia.get('disabled_reason', '') or '')
    quota = nvidia.get('quota', {}) if isinstance(nvidia.get('quota'), dict) else {}
    quota_state = str(quota.get('state', 'unknown') or 'unknown')
    quota_sufficient = reason not in {'quota_exhausted', 'payment_required'} and quota_state not in {
        'exhausted',
        'blocked',
    }
    return {
        'quota_sufficient': quota_sufficient,
        'services_healthy': bool(nvidia.get('enabled', False)) and quota_sufficient,
    }


def load_public_provider_status(
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 5.0,
) -> dict[str, Any]:
    request = Request(
        'http://127.0.0.1:5001/api/trevor/providers',
        headers={'Accept': 'application/json'},
        method='GET',
    )
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, dict) or not isinstance(payload.get('providers'), list):
        raise RuntimeError('provider_status_invalid')
    return payload


def load_signals(
    data_root: Path,
    config: AutonomyConfig,
    *,
    provider_status_loader: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        import psutil

        cpu_percent = float(psutil.cpu_percent(interval=0.1))
        memory_percent = float(psutil.virtual_memory().percent)
    except Exception:
        cpu_percent = 0.0
        memory_percent = 0.0

    loader = provider_status_loader or load_public_provider_status
    try:
        public_status = loader()
    except Exception:
        public_status = {}
    signals = provider_signals(public_status)
    signals.update(
        {
            'user_active': user_is_active(
                data_root, window_seconds=config.user_active_window_seconds
            ),
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
        }
    )
    return signals


def skill_stability(root: Path) -> dict[str, Any]:
    def signatures(base: Path) -> dict[str, str]:
        result = {}
        if not base.exists():
            return result
        for path in base.glob('*/SKILL.md'):
            try:
                first_line = path.read_text(encoding='utf-8').splitlines()[0].strip()
            except (OSError, IndexError):
                first_line = ''
            result[path.parent.name] = first_line
        return result

    local = signatures(root / 'skills')
    imported = signatures(root / '.gemini' / 'skills')
    shared = sorted(set(local) & set(imported))
    conflicts = [name for name in shared if local[name] != imported[name]]
    return {
        'stable': not conflicts,
        'conflict_count': len(conflicts),
        'conflicts': conflicts,
    }


def enqueue_nightly(queue: AutonomyQueue, *, hour: int) -> dict[str, Any] | None:
    local_now = datetime.now().astimezone()
    if local_now.hour != int(hour):
        return None
    nightly_date = local_now.date().isoformat()
    if any(
        isinstance(task.get('metadata'), dict)
        and task['metadata'].get('nightly_date') == nightly_date
        for task in queue.tasks()
    ):
        return None
    return queue.enqueue(
        '執行夜間深度維護：檢查記憶衝突、Provider 健康度、測試與內容一致性',
        capability_mode='general',
        category='maintenance',
        priority=20,
        metadata={'nightly_date': nightly_date, 'system_generated': True},
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trevor autonomy daemon')
    parser.add_argument('--heartbeat', '--interval', dest='heartbeat', type=int, default=60)
    parser.add_argument('--evaluation', type=int, default=900)
    parser.add_argument('--nightly-hour', type=int, default=3)
    parser.add_argument('--once', action='store_true')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--scheduler-only', action='store_true')
    modes.add_argument('--worker-only', action='store_true')
    return parser.parse_args(argv)


def run_daemon(args: argparse.Namespace) -> int:
    data_root = resolve_data_root(ROOT)
    config = AutonomyConfig(
        heartbeat_seconds=max(5, int(args.heartbeat)),
        evaluation_seconds=max(60, int(args.evaluation)),
        nightly_maintenance_hour=max(0, min(23, int(args.nightly_hour))),
    )
    autonomy_root = data_root / 'autonomy'
    mode = 'scheduler' if args.scheduler_only else ('worker' if args.worker_only else 'combined')
    state_path = autonomy_root / (
        'daemon_state.json' if mode == 'combined' else f'{mode}_state.json'
    )
    queue = AutonomyQueue(autonomy_root / 'task_queue.json')
    audit_log = HashChainAuditLog(data_root / 'audit' / 'events.jsonl')
    runner = None
    if not args.scheduler_only:
        executor_instance = None

        def execute_task(
            task: dict[str, Any],
            *,
            cancellation: Any = None,
        ) -> dict[str, Any]:
            nonlocal executor_instance
            if executor_instance is None:
                from core.autonomy_executor import TrevorTaskExecutor

                executor_instance = TrevorTaskExecutor(ROOT, data_root, audit_log=audit_log)
            return executor_instance(task, cancellation=cancellation)

        runner = AutonomyRunner(data_root, executor=execute_task, config=config)
    stop = threading.Event()

    def request_stop(signum: int, frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    audit_log.append(
        'autonomy_daemon_started',
        {
            'heartbeat_seconds': config.heartbeat_seconds,
            'evaluation_seconds': config.evaluation_seconds,
            'mode': mode,
        },
    )
    next_evaluation = 0.0
    last_execution: dict[str, Any] = {'status': 'not_evaluated'}

    while not stop.is_set():
        cycle_started = time.monotonic()
        signals = load_signals(data_root, config)
        nightly = (
            None
            if args.worker_only
            else enqueue_nightly(queue, hour=config.nightly_maintenance_hour)
        )
        if nightly:
            audit_log.append('autonomy_nightly_enqueued', {'task_id': nightly['id']})
        if runner is not None and cycle_started >= next_evaluation:
            last_execution = runner.evaluate_once(signals)
            next_evaluation = cycle_started + config.evaluation_seconds

        tasks = queue.tasks()
        stability = skill_stability(ROOT)
        _atomic_json(
            state_path,
            {
                'schema_version': 1,
                'identity': {'agent': 'trevor', 'role': '崔佛'},
                'daemon_status': 'running',
                'mode': mode,
                'heartbeat_at': datetime.now(timezone.utc).isoformat(),
                'heartbeat_seconds': config.heartbeat_seconds,
                'evaluation_seconds': config.evaluation_seconds,
                'pending_tasks': sum(task.get('status') == 'pending' for task in tasks),
                'running_tasks': sum(task.get('status') == 'running' for task in tasks),
                'signals': signals,
                'skill_stability': stability,
                'last_execution': last_execution,
            },
        )
        if args.once:
            break
        elapsed = time.monotonic() - cycle_started
        stop.wait(max(1.0, config.heartbeat_seconds - elapsed))

    _atomic_json(
        state_path,
        {
            'schema_version': 1,
            'identity': {'agent': 'trevor', 'role': '崔佛'},
            'daemon_status': 'stopped' if stop.is_set() else 'completed_once',
            'mode': mode,
            'heartbeat_at': datetime.now(timezone.utc).isoformat(),
            'last_execution': last_execution,
        },
    )
    audit_log.append('autonomy_daemon_stopped', {'once': bool(args.once), 'mode': mode})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_daemon(parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())

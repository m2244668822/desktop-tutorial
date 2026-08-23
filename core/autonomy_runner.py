from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Callable

from core.autonomy import AutonomyConfig, AutonomyLease, AutonomyPolicy, AutonomyQueue


class AutonomyRunner:
    def __init__(
        self,
        data_root: str | Path,
        *,
        worker_id: str | None = None,
        executor: Callable[[dict[str, Any]], dict[str, Any]],
        config: AutonomyConfig | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.config = config or AutonomyConfig()
        self.worker_id = worker_id or f'{socket.gethostname()}-{os.getpid()}'
        autonomy_root = self.data_root / 'autonomy'
        self.queue = AutonomyQueue(autonomy_root / 'task_queue.json')
        self.lease = AutonomyLease(
            autonomy_root / 'task.lease', ttl_seconds=self.config.lease_ttl_seconds
        )
        self.policy = AutonomyPolicy(self.config)
        self.executor = executor

    def evaluate_once(self, signals: dict[str, Any]) -> dict[str, Any]:
        if not self.lease.acquire(self.worker_id):
            return {'status': 'busy', 'reason': 'task_lease_unavailable'}
        try:
            task = self.queue.claim_next(self.worker_id)
            if task is None:
                return {'status': 'idle', 'reason': 'no_pending_task'}

            decision = self.policy.evaluate(task, signals)
            reason = str(decision.get('reason', 'policy_rejected'))
            if not decision.get('allowed'):
                if reason in {
                    'user_active',
                    'high_cpu',
                    'high_memory',
                    'quota_insufficient',
                    'service_unhealthy',
                }:
                    self.queue.defer(task['id'], reason=reason)
                    return {'status': 'paused', 'reason': reason, 'task_id': task['id']}
                self.queue.finish(task['id'], success=False, error=reason)
                return {'status': 'rejected', 'reason': reason, 'task_id': task['id']}

            try:
                result = self.executor(task)
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'[:1000]
                self.queue.finish(task['id'], success=False, error=error)
                return {'status': 'failed', 'error': error, 'task_id': task['id']}

            self.queue.finish(task['id'], success=True, result=result)
            return {'status': 'completed', 'task_id': task['id'], 'result': result}
        finally:
            self.lease.release(self.worker_id)


__all__ = ['AutonomyRunner']

from __future__ import annotations

import os
import socket
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from core.autonomy import AutonomyConfig, AutonomyLease, AutonomyPolicy, AutonomyQueue


@contextmanager
def _renew_running_claim(
    queue: AutonomyQueue,
    task_id: str,
    worker_id: str,
    interval_seconds: float,
):
    stop = threading.Event()
    renewal_interval = max(0.01, float(interval_seconds))
    retry_interval = min(5.0, max(0.01, renewal_interval / 4))

    def renew() -> None:
        wait_seconds = renewal_interval
        while not stop.wait(wait_seconds):
            try:
                renewed = queue.renew_claim(task_id, worker_id)
            except Exception:
                wait_seconds = retry_interval
                continue
            if not renewed:
                return
            wait_seconds = renewal_interval

    thread = threading.Thread(
        target=renew,
        name=f'trevor-claim-renewal-{task_id}',
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


class AutonomyRunner:
    def __init__(
        self,
        data_root: str | Path,
        *,
        worker_id: str | None = None,
        executor: Callable[[dict[str, Any]], dict[str, Any]],
        config: AutonomyConfig | None = None,
        renewal_interval_seconds: float | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.config = config or AutonomyConfig()
        self.worker_id = worker_id or f'{socket.gethostname()}-{os.getpid()}'
        autonomy_root = self.data_root / 'autonomy'
        self.claim_ttl_seconds = max(60, int(self.config.lease_ttl_seconds))
        self.queue = AutonomyQueue(
            autonomy_root / 'task_queue.json',
            claim_ttl_seconds=self.claim_ttl_seconds,
        )
        self.lease = AutonomyLease(
            autonomy_root / 'task.lease', ttl_seconds=self.config.lease_ttl_seconds
        )
        self.policy = AutonomyPolicy(self.config)
        self.executor = executor
        requested_renewal_interval = (
            max(
                1.0,
                min(
                    self.config.heartbeat_seconds,
                    self.claim_ttl_seconds / 3,
                ),
            )
            if renewal_interval_seconds is None
            else max(0.01, float(renewal_interval_seconds))
        )
        self.renewal_interval_seconds = min(
            requested_renewal_interval,
            self.claim_ttl_seconds / 3,
        )

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
                    deferred = self.queue.defer(
                        task['id'], worker_id=self.worker_id, reason=reason
                    )
                    if not deferred:
                        return {
                            'status': 'lease_lost',
                            'error': 'task_claim_lost',
                            'task_id': task['id'],
                        }
                    return {'status': 'paused', 'reason': reason, 'task_id': task['id']}
                self.queue.finish(
                    task['id'], worker_id=self.worker_id, success=False, error=reason
                )
                return {'status': 'rejected', 'reason': reason, 'task_id': task['id']}

            with _renew_running_claim(
                self.queue,
                task['id'],
                self.worker_id,
                self.renewal_interval_seconds,
            ):
                try:
                    result = self.executor(task)
                except Exception as exc:
                    error = f'{type(exc).__name__}: {exc}'[:1000]
                    finished = self.queue.finish(
                        task['id'],
                        worker_id=self.worker_id,
                        success=False,
                        error=error,
                    )
                    if not finished:
                        return {
                            'status': 'lease_lost',
                            'error': 'task_claim_lost',
                            'task_id': task['id'],
                        }
                    return {'status': 'failed', 'error': error, 'task_id': task['id']}

                if not self.queue.finish(
                    task['id'],
                    worker_id=self.worker_id,
                    success=True,
                    result=result,
                ):
                    return {
                        'status': 'lease_lost',
                        'error': 'task_claim_lost',
                        'task_id': task['id'],
                    }
                return {'status': 'completed', 'task_id': task['id'], 'result': result}
        finally:
            self.lease.release(self.worker_id)


__all__ = ['AutonomyRunner']

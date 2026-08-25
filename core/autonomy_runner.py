from __future__ import annotations

import inspect
import os
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.autonomy import AutonomyConfig, AutonomyLease, AutonomyPolicy, AutonomyQueue
from core.autonomy_claim import ClaimCancellation, ClaimLostError


def _supports_keyword_argument(callback: Callable[..., Any], name: str) -> bool:
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or (
            parameter.name == name
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        )
        for parameter in parameters
    )


def _initial_claim_seconds(
    queue: AutonomyQueue,
    lease_expires_at: str,
    claim_ttl_seconds: float,
) -> float:
    try:
        expires_at = datetime.fromisoformat(
            str(lease_expires_at or '').replace('Z', '+00:00')
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = queue.now().astimezone(timezone.utc)
        return max(
            0.0,
            min(
                claim_ttl_seconds,
                (expires_at.astimezone(timezone.utc) - now).total_seconds(),
            ),
        )
    except (AttributeError, TypeError, ValueError):
        return claim_ttl_seconds


@contextmanager
def _renew_running_claim(
    queue: AutonomyQueue,
    task_id: str,
    worker_id: str,
    interval_seconds: float,
    claim_ttl_seconds: float | None = None,
    lease_expires_at: str = '',
):
    stop = threading.Event()
    cancellation = ClaimCancellation()
    renewal_interval = max(0.01, float(interval_seconds))
    retry_interval = min(5.0, max(0.01, renewal_interval / 4))
    claim_ttl = max(
        0.01,
        float(
            claim_ttl_seconds
            if claim_ttl_seconds is not None
            else getattr(queue, 'claim_ttl_seconds', renewal_interval * 3)
        ),
    )
    confirmed_until = time.monotonic() + _initial_claim_seconds(
        queue,
        lease_expires_at,
        claim_ttl,
    )
    deadline_condition = threading.Condition()
    if time.monotonic() >= confirmed_until:
        cancellation.mark_lost()

    def watch_deadline() -> None:
        with deadline_condition:
            while not stop.is_set() and not cancellation.is_lost():
                remaining = confirmed_until - time.monotonic()
                if remaining <= 0:
                    cancellation.mark_lost()
                    return
                deadline_condition.wait(timeout=remaining)

    def renew() -> None:
        nonlocal confirmed_until
        wait_seconds = renewal_interval
        while True:
            remaining = confirmed_until - time.monotonic()
            if remaining <= 0:
                cancellation.mark_lost()
                return
            if stop.wait(min(wait_seconds, remaining)):
                return
            if cancellation.is_lost():
                return
            if time.monotonic() >= confirmed_until:
                cancellation.mark_lost()
                return
            try:
                renewed = queue.renew_claim(task_id, worker_id)
            except Exception:
                if time.monotonic() >= confirmed_until:
                    cancellation.mark_lost()
                    return
                wait_seconds = retry_interval
                continue
            if not renewed:
                cancellation.mark_lost()
                with deadline_condition:
                    deadline_condition.notify_all()
                return
            if cancellation.is_lost():
                return
            with deadline_condition:
                confirmed_until = time.monotonic() + claim_ttl
                deadline_condition.notify_all()
            wait_seconds = renewal_interval

    watchdog = threading.Thread(
        target=watch_deadline,
        name=f'trevor-claim-deadline-{task_id}',
        daemon=True,
    )
    thread = threading.Thread(
        target=renew,
        name=f'trevor-claim-renewal-{task_id}',
        daemon=True,
    )
    watchdog.start()
    thread.start()
    try:
        yield cancellation
    finally:
        stop.set()
        with deadline_condition:
            deadline_condition.notify_all()
        watchdog.join(timeout=1)
        thread.join(timeout=5)


class AutonomyRunner:
    def __init__(
        self,
        data_root: str | Path,
        *,
        worker_id: str | None = None,
        executor: Callable[..., dict[str, Any]],
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
                finished = self.queue.finish(
                    task['id'], worker_id=self.worker_id, success=False, error=reason
                )
                if not finished:
                    return {
                        'status': 'lease_lost',
                        'error': 'task_claim_lost',
                        'task_id': task['id'],
                    }
                return {'status': 'rejected', 'reason': reason, 'task_id': task['id']}

            with _renew_running_claim(
                self.queue,
                task['id'],
                self.worker_id,
                self.renewal_interval_seconds,
                self.queue.claim_ttl_seconds,
                str(task.get('lease_expires_at', '') or ''),
            ) as cancellation:
                finalization_started = False

                def begin_finalization() -> None:
                    nonlocal finalization_started
                    cancellation.raise_if_lost()
                    if finalization_started:
                        return
                    if not self.queue.begin_finalization(
                        task['id'], worker_id=self.worker_id
                    ):
                        cancellation.mark_lost()
                        cancellation.raise_if_lost()
                    finalization_started = True

                try:
                    cancellation.raise_if_lost()
                    execution_task = dict(task)
                    executor_options: dict[str, Any] = {}
                    if _supports_keyword_argument(self.executor, 'cancellation'):
                        executor_options['cancellation'] = cancellation
                    if _supports_keyword_argument(self.executor, 'before_publish'):
                        executor_options['before_publish'] = begin_finalization
                    result = self.executor(execution_task, **executor_options)
                    cancellation.raise_if_lost()
                except ClaimLostError:
                    if finalization_started:
                        error = 'task_claim_lost_during_finalization'
                        failed = self.queue.finish(
                            task['id'],
                            worker_id=self.worker_id,
                            success=False,
                            error=error,
                        )
                        if failed:
                            return {
                                'status': 'failed',
                                'error': error,
                                'task_id': task['id'],
                            }
                    return {
                        'status': 'lease_lost',
                        'error': 'task_claim_lost',
                        'task_id': task['id'],
                    }
                except Exception as exc:
                    if cancellation.is_lost():
                        if finalization_started:
                            error = 'task_claim_lost_during_finalization'
                            failed = self.queue.finish(
                                task['id'],
                                worker_id=self.worker_id,
                                success=False,
                                error=error,
                            )
                            if failed:
                                return {
                                    'status': 'failed',
                                    'error': error,
                                    'task_id': task['id'],
                                }
                        return {
                            'status': 'lease_lost',
                            'error': 'task_claim_lost',
                            'task_id': task['id'],
                        }
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

                try:
                    finished = self.queue.finish(
                        task['id'],
                        worker_id=self.worker_id,
                        success=True,
                        result=result,
                    )
                except (TypeError, ValueError) as exc:
                    error = f'executor_result_not_serializable: {type(exc).__name__}'
                    failed = self.queue.finish(
                        task['id'],
                        worker_id=self.worker_id,
                        success=False,
                        error=error,
                    )
                    if not failed:
                        return {
                            'status': 'lease_lost',
                            'error': 'task_claim_lost',
                            'task_id': task['id'],
                        }
                    return {
                        'status': 'failed',
                        'error': error,
                        'task_id': task['id'],
                    }
                if not finished:
                    return {
                        'status': 'lease_lost',
                        'error': 'task_claim_lost',
                        'task_id': task['id'],
                    }
                return {'status': 'completed', 'task_id': task['id'], 'result': result}
        finally:
            self.lease.release(self.worker_id)


__all__ = ['AutonomyRunner']

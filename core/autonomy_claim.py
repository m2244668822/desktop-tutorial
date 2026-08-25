from __future__ import annotations

import threading


class ClaimLostError(RuntimeError):
    pass


class ClaimCancellation:
    def __init__(self) -> None:
        self._lost = threading.Event()

    def mark_lost(self) -> None:
        self._lost.set()

    def is_lost(self) -> bool:
        return self._lost.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._lost.wait(timeout)

    def raise_if_lost(self) -> None:
        if self.is_lost():
            raise ClaimLostError('task_claim_lost')


__all__ = [
    'ClaimCancellation',
    'ClaimLostError',
]

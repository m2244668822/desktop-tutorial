"""Session-scoped conversation state for Trevor's single chat entry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic
from typing import Any, Iterable, Mapping


@dataclass
class _SessionState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_action: str = ""
    updated_at: float = field(default_factory=monotonic)


class SessionConversationStore:
    """Keep short-term dialogue and pending actions isolated by session id."""

    def __init__(self, *, max_messages: int = 80, max_sessions: int = 128):
        self.max_messages = max(4, int(max_messages))
        self.max_sessions = max(4, int(max_sessions))
        self._sessions: dict[str, _SessionState] = {}
        self._lock = RLock()

    @staticmethod
    def normalize_session_id(session_id: str | None) -> str:
        value = str(session_id or "").strip()
        return value[:128] if value else "default"

    def _state_unlocked(self, session_id: str | None) -> _SessionState:
        key = self.normalize_session_id(session_id)
        state = self._sessions.get(key)
        if state is None:
            if len(self._sessions) >= self.max_sessions:
                oldest = min(
                    self._sessions,
                    key=lambda item: self._sessions[item].updated_at,
                )
                del self._sessions[oldest]
            state = _SessionState()
            self._sessions[key] = state
        state.updated_at = monotonic()
        return state

    @staticmethod
    def _normalize_history(
        conversation: Iterable[Mapping[str, Any]] | None,
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in conversation or ():
            if not isinstance(item, Mapping):
                continue
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", item.get("text", "")) or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content[:12000]})
        return normalized

    def hydrate(
        self,
        session_id: str | None,
        conversation: Iterable[Mapping[str, Any]] | None,
    ) -> bool:
        """Seed an empty server session from trusted-shape client history once."""
        normalized = self._normalize_history(conversation)
        if not normalized:
            return False
        with self._lock:
            state = self._state_unlocked(session_id)
            if state.messages:
                return False
            state.messages = normalized[-self.max_messages :]
            state.updated_at = monotonic()
            return True

    def messages(self, session_id: str | None, *, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            state = self._state_unlocked(session_id)
            selected = state.messages[-max(1, int(limit)) :] if limit else state.messages
            return deepcopy(selected)

    def append_turn(
        self,
        session_id: str | None,
        user_message: str,
        assistant_message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        user_text = str(user_message or "").strip()
        assistant_text = str(assistant_message or "").strip()
        with self._lock:
            state = self._state_unlocked(session_id)
            if user_text:
                state.messages.append(
                    {
                        "role": "user",
                        "content": user_text[:12000],
                        "metadata": dict(metadata or {}),
                    }
                )
            if assistant_text:
                state.messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_text[:24000],
                        "metadata": dict(metadata or {}),
                    }
                )
            if len(state.messages) > self.max_messages:
                state.messages = state.messages[-self.max_messages :]
            state.updated_at = monotonic()

    def set_pending_action(self, session_id: str | None, message: str) -> None:
        with self._lock:
            state = self._state_unlocked(session_id)
            state.pending_action = str(message or "").strip()[:12000]

    def pending_action(self, session_id: str | None) -> str:
        with self._lock:
            return self._state_unlocked(session_id).pending_action

    def take_pending_action(self, session_id: str | None) -> str:
        with self._lock:
            state = self._state_unlocked(session_id)
            message = state.pending_action
            state.pending_action = ""
            state.updated_at = monotonic()
            return message

    def clear_pending_action(self, session_id: str | None) -> None:
        with self._lock:
            state = self._state_unlocked(session_id)
            state.pending_action = ""

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)


__all__ = ["SessionConversationStore"]

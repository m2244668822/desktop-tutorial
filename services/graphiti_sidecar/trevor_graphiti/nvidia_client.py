from __future__ import annotations

from typing import Any


class _NvidiaCompletions:
    def __init__(self, delegate: Any):
        self._delegate = delegate

    async def create(self, **kwargs: Any) -> Any:
        extra_body = dict(kwargs.pop('extra_body', {}) or {})
        chat_template_kwargs = dict(extra_body.get('chat_template_kwargs', {}) or {})
        chat_template_kwargs['enable_thinking'] = False
        extra_body['chat_template_kwargs'] = chat_template_kwargs
        return await self._delegate.create(extra_body=extra_body, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _NvidiaChat:
    def __init__(self, delegate: Any):
        self._delegate = delegate
        self.completions = _NvidiaCompletions(delegate.completions)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class NvidiaNoThinkingClient:
    def __init__(self, delegate: Any):
        self._delegate = delegate
        self.chat = _NvidiaChat(delegate.chat)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


__all__ = ['NvidiaNoThinkingClient']

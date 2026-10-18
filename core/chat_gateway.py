"""Low-traffic chat routing kept separate from MCP permission decisions."""

from __future__ import annotations

import json
import urllib.error as urllib_error
import urllib.request as urllib_request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from core.model_router import ModelProvider, ModelRouter, RetryPolicy


class ChatGatewayBlocked(RuntimeError):
    """The chat request could not be completed by an eligible provider."""


@dataclass(frozen=True)
class ChatRequest:
    task_id: str
    run_id: str
    messages: Sequence[Mapping[str, Any]]
    role: str = "chat"
    privacy_class: str = "local"
    preferred_model: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.2
    extra_body: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResponse:
    status: str
    content: str
    provider: str
    model_id: str
    task_id: str
    run_id: str
    attempted_models: tuple[str, ...]
    fallback_used: bool
    reasoning_details: Any = None
    tool_calls: Any = None

    def as_assistant_message(self) -> dict[str, Any]:
        """Build a continuation-safe assistant message.

        OpenRouter reasoning metadata is opaque provider state. Preserve it
        byte-for-byte for a same-model continuation, but never execute the
        returned tool calls here. Policy and MCP orchestration remain separate.
        """
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.reasoning_details is not None:
            message["reasoning_details"] = self.reasoning_details
        if self.tool_calls is not None:
            message["tool_calls"] = self.tool_calls
        return message

    def continuation_messages(
        self,
        previous_messages: Sequence[Mapping[str, Any]],
        user_content: str,
    ) -> list[dict[str, Any]]:
        """Build a same-model follow-up without stripping provider metadata."""
        if not isinstance(user_content, str) or not user_content.strip():
            raise ChatGatewayBlocked("continuation_message_empty")
        messages = [dict(message) for message in previous_messages]
        messages.append(self.as_assistant_message())
        messages.append({"role": "user", "content": user_content})
        return messages


class ChatTransport(Protocol):
    def generate(self, provider: ModelProvider, payload: dict[str, Any]) -> str: ...


class ChatModelGateway:
    """One chat entry point with local-first and bounded fallback routing."""

    def __init__(
        self,
        router: ModelRouter,
        transport: ChatTransport,
        *,
        retry: RetryPolicy | None = None,
    ):
        self.router = router
        self.transport = transport
        self.retry = retry or RetryPolicy()

    def complete(
        self,
        request: ChatRequest,
        *,
        allowed_models: set[str] | None = None,
    ) -> ChatResponse:
        self._validate(request)
        providers = self.router.candidates(
            role=request.role,
            privacy_class=request.privacy_class,
            preferred_model=request.preferred_model,
            capability="chat",
        )
        if allowed_models is not None:
            providers = [provider for provider in providers if provider.model_id in allowed_models]
        if not providers:
            raise ChatGatewayBlocked("no_chat_provider")

        attempted: list[str] = []
        for provider in providers:
            attempted.append(provider.model_id)
            payload = self._payload(request, provider)
            try:
                raw_response = self.router.call_model(
                    provider.model_id,
                    lambda selected: self._generate(selected, payload),
                    retry=self.retry,
                    requested_tokens=payload["max_tokens"],
                )
            except Exception:
                continue
            if isinstance(raw_response, Mapping):
                content = raw_response.get("content", "")
                reasoning_details = raw_response.get("reasoning_details")
                tool_calls = raw_response.get("tool_calls")
            else:
                content = raw_response
                reasoning_details = None
                tool_calls = None
            if not isinstance(content, str) or not content.strip():
                continue
            return ChatResponse(
                status="complete",
                content=content,
                provider=provider.provider,
                model_id=provider.model_id,
                task_id=request.task_id,
                run_id=request.run_id,
                attempted_models=tuple(attempted),
                fallback_used=len(attempted) > 1,
                reasoning_details=reasoning_details,
                tool_calls=tool_calls,
            )
        raise ChatGatewayBlocked("chat_providers_exhausted")

    def continue_chat(
        self,
        request: ChatRequest,
        previous_response: ChatResponse,
        user_content: str,
    ) -> ChatResponse:
        """Continue reasoning on the exact model that produced the response.

        OpenRouter reasoning metadata is provider-specific. A continuation must
        therefore fail closed when that exact model is unavailable instead of
        sending the metadata to a fallback model.
        """
        continuation = ChatRequest(
            task_id=request.task_id,
            run_id=request.run_id,
            messages=previous_response.continuation_messages(
                request.messages,
                user_content,
            ),
            role=request.role,
            privacy_class=request.privacy_class,
            preferred_model=previous_response.model_id,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            extra_body=request.extra_body,
        )
        return self.complete(
            continuation,
            allowed_models={previous_response.model_id},
        )

    @staticmethod
    def _validate(request: ChatRequest) -> None:
        if not request.task_id.strip() or not request.run_id.strip():
            raise ChatGatewayBlocked("chat_identity_missing")
        if not request.messages:
            raise ChatGatewayBlocked("chat_messages_empty")

    @staticmethod
    def _payload(request: ChatRequest, provider: ModelProvider) -> dict[str, Any]:
        requested_tokens = max(1, int(request.max_tokens))
        provider_cap = max(1, int(provider.max_output_tokens))
        payload = {
            "model": provider.model_id,
            "messages": [dict(message) for message in request.messages],
            "stream": False,
            "max_tokens": min(requested_tokens, provider_cap),
            "temperature": request.temperature,
        }
        for key, value in request.extra_body.items():
            if key not in payload:
                payload[str(key)] = value
        return payload

    def _generate(self, provider: ModelProvider, payload: dict[str, Any]) -> Any:
        generate_response = getattr(self.transport, "generate_response", None)
        if callable(generate_response):
            return generate_response(provider, payload)
        return self.transport.generate(provider, payload)


class RegistryChatTransport:
    """Adapt the existing ProviderRegistry/ProviderHttpClient pair."""

    def __init__(self, registry, client=None):
        if client is None:
            from core.provider_client import ProviderHttpClient

            client = ProviderHttpClient(registry)
        self.registry = registry
        self.client = client

    def generate(self, provider: ModelProvider, payload: dict[str, Any]) -> str:
        result = self.generate_response(provider, payload)
        return str(result.get("content", ""))

    def generate_response(self, provider: ModelProvider, payload: dict[str, Any]) -> dict[str, Any]:
        spec = self.registry.get(provider.provider)
        call_with_metadata = getattr(self.client, "call_with_metadata", None)
        if callable(call_with_metadata):
            result = call_with_metadata(spec, payload)
            return dict(result) if isinstance(result, Mapping) else {"content": str(result)}
        return {"content": str(self.client.call(spec, payload))}


class OllamaChatTransport:
    """Transport for a local Ollama chat endpoint without API credentials."""

    def __init__(self, *, endpoint: str = "http://127.0.0.1:11434/api/chat", timeout: float = 45.0):
        self.endpoint = str(endpoint or "").strip()
        self.timeout = max(1.0, float(timeout))

    def generate(self, provider: ModelProvider, payload: dict[str, Any]) -> str:
        wire = dict(payload)
        wire["model"] = provider.model_id
        wire["stream"] = False
        options = dict(wire.pop("options", {}) or {})
        if "temperature" in wire:
            options.setdefault("temperature", wire.pop("temperature"))
        if "max_tokens" in wire:
            options.setdefault("num_predict", wire.pop("max_tokens"))
        if options:
            wire["options"] = options
        request = urllib_request.Request(
            self.endpoint,
            data=json.dumps(wire, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            raise RuntimeError(f"ollama_http_{exc.code}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError("ollama_unreachable") from exc
        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("ollama_invalid_json") from exc
        message = parsed.get("message", {}) if isinstance(parsed, Mapping) else {}
        content = message.get("content", "") if isinstance(message, Mapping) else ""
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("ollama_empty_response")
        return content.strip()


class CompositeChatTransport:
    """Route local Ollama and registry-backed providers through one interface."""

    def __init__(self, *, local: ChatTransport, registry: ChatTransport):
        self.local = local
        self.registry = registry

    def generate(self, provider: ModelProvider, payload: dict[str, Any]) -> Any:
        if provider.provider == "ollama":
            return self.local.generate(provider, payload)
        return self.registry.generate(provider, payload)

    def generate_response(self, provider: ModelProvider, payload: dict[str, Any]) -> Any:
        if provider.provider == "ollama":
            return {"content": self.local.generate(provider, payload)}
        generate_response = getattr(self.registry, "generate_response", None)
        if callable(generate_response):
            return generate_response(provider, payload)
        return {"content": self.registry.generate(provider, payload)}


__all__ = [
    "ChatGatewayBlocked",
    "ChatModelGateway",
    "ChatRequest",
    "ChatResponse",
    "CompositeChatTransport",
    "OllamaChatTransport",
    "RegistryChatTransport",
]

"""Deterministic provider selection without granting tool permissions."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Iterable


class ModelUnavailable(RuntimeError):
    pass


class ModelCallError(RuntimeError):
    pass


@dataclass
class ModelProvider:
    model_id: str
    provider: str
    roles: set[str] = field(default_factory=set)
    privacy_class: str = "local"
    supports_tools: bool = False
    supports_streaming: bool = False
    supports_json_schema: bool = False
    max_concurrency: int = 1
    priority: int = 100
    availability: str = "unknown"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0


@dataclass
class Circuit:
    failures: int = 0
    threshold: int = 3
    open: bool = False


class ModelRouter:
    def __init__(self, providers: Iterable[ModelProvider]):
        self.providers = {item.model_id: item for item in providers}
        self.circuits = {item.model_id: Circuit() for item in self.providers.values()}

    def health(self, model_id: str, availability: str) -> None:
        self.providers[model_id].availability = availability
        if availability == "online":
            self.circuits[model_id].open = False
            self.circuits[model_id].failures = 0

    def record_success(self, model_id: str) -> None:
        circuit = self.circuits[model_id]
        circuit.failures = 0
        circuit.open = False
        self.providers[model_id].availability = "online"

    def record_failure(self, model_id: str) -> None:
        circuit = self.circuits[model_id]
        circuit.failures += 1
        if circuit.failures >= circuit.threshold:
            circuit.open = True
            self.providers[model_id].availability = "unavailable"
        else:
            self.providers[model_id].availability = "degraded"

    def call_model(self, model_id: str, operation, *, retry: RetryPolicy | None = None, sleep=time.sleep):
        """Retry model generation only; never use this for MCP mutations."""
        if model_id not in self.providers or self.circuits[model_id].open:
            raise ModelUnavailable("provider_circuit_open")
        policy = retry or RetryPolicy()
        attempts = max(1, int(policy.max_attempts))
        last_error = None
        for attempt in range(attempts):
            try:
                result = operation(self.providers[model_id])
                self.record_success(model_id)
                return result
            except Exception as exc:  # provider adapters normalize errors at the boundary
                last_error = exc
                self.record_failure(model_id)
                if attempt + 1 < attempts and not self.circuits[model_id].open:
                    delay = min(policy.max_delay_seconds, policy.base_delay_seconds * (2**attempt))
                    sleep(delay)
        raise ModelCallError(str(last_error or "model_call_failed")) from last_error

    @classmethod
    def from_runtime_registry(cls, registry, *, local_model: str = "qwen2.5:7b") -> "ModelRouter":
        """Adapt the existing runtime ProviderRegistry without duplicating credentials."""
        providers = [
            ModelProvider(
                model_id=local_model,
                provider="ollama",
                roles={"planner", "fallback"},
                privacy_class="local",
                supports_tools=True,
                supports_streaming=True,
                supports_json_schema=True,
                max_concurrency=1,
                priority=1,
                availability="unknown",
            )
        ]
        for spec in getattr(registry, "_specs", {}).values():
            state = registry.state(spec.name)
            providers.append(
                ModelProvider(
                    model_id=registry.model_for(spec.name),
                    provider=spec.name,
                    roles={"planner", "fallback"},
                    privacy_class="cloud",
                    supports_tools=False,
                    max_concurrency=1,
                    priority=10,
                    availability="online" if registry.is_available(spec.name) else "unavailable",
                )
            )
        return cls(providers)

    def select(
        self,
        *,
        role: str,
        privacy_class: str = "local",
        requires_tools: bool = False,
        preferred_model: str | None = None,
    ) -> ModelProvider:
        candidates = list(self.providers.values())
        if preferred_model:
            candidates.sort(key=lambda item: (item.model_id != preferred_model, item.priority))
        else:
            candidates.sort(key=lambda item: item.priority)
        for item in candidates:
            if role not in item.roles and "general" not in item.roles:
                continue
            if item.availability != "online" or self.circuits[item.model_id].open:
                continue
            if requires_tools and not item.supports_tools:
                continue
            if privacy_class == "local" and item.privacy_class != "local":
                continue
            return item
        raise ModelUnavailable("no_provider_available")

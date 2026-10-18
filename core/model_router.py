"""Deterministic provider selection without granting tool permissions."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
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
    capabilities: set[str] = field(default_factory=lambda: {"chat"})
    max_output_tokens: int = 4096
    token_budget_per_minute: int | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    concurrency_wait_seconds: float = 0.0


@dataclass
class Circuit:
    failures: int = 0
    threshold: int = 3
    open: bool = False


class ModelRouter:
    def __init__(self, providers: Iterable[ModelProvider]):
        self.providers = {item.model_id: item for item in providers}
        self.circuits = {item.model_id: Circuit() for item in self.providers.values()}
        self._semaphores = {
            item.model_id: threading.BoundedSemaphore(max(1, int(item.max_concurrency)))
            for item in self.providers.values()
        }
        self._budget_lock = threading.Lock()
        self._budget_windows = {
            item.model_id: (time.monotonic(), 0) for item in self.providers.values()
        }

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

    def _reserve_tokens(self, model_id: str, requested_tokens: int | None) -> None:
        limit = self.providers[model_id].token_budget_per_minute
        if limit is None or requested_tokens is None:
            return
        tokens = max(0, int(requested_tokens))
        now = time.monotonic()
        with self._budget_lock:
            started, used = self._budget_windows[model_id]
            if now - started >= 60.0:
                started, used = now, 0
            if used + tokens > max(0, int(limit)):
                self._budget_windows[model_id] = (started, used)
                raise ModelUnavailable("provider_token_budget_exhausted")
            self._budget_windows[model_id] = (started, used + tokens)

    def call_model(
        self,
        model_id: str,
        operation,
        *,
        retry: RetryPolicy | None = None,
        requested_tokens: int | None = None,
        sleep=time.sleep,
    ):
        """Run bounded model generation; never use this for MCP mutations."""
        if model_id not in self.providers or self.circuits[model_id].open:
            raise ModelUnavailable("provider_circuit_open")
        policy = retry or RetryPolicy()
        semaphore = self._semaphores[model_id]
        if not semaphore.acquire(timeout=max(0.0, float(policy.concurrency_wait_seconds))):
            raise ModelUnavailable("provider_concurrency_limit")
        try:
            self._reserve_tokens(model_id, requested_tokens)
        except Exception:
            semaphore.release()
            raise
        attempts = max(1, int(policy.max_attempts))
        last_error = None
        try:
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
        finally:
            semaphore.release()

    @classmethod
    def from_runtime_registry(cls, registry, *, local_model: str = "qwen2.5:7b") -> "ModelRouter":
        """Adapt the existing runtime ProviderRegistry without duplicating credentials."""
        providers = [
            ModelProvider(
                model_id=local_model,
                provider="ollama",
                roles={"planner", "fallback", "chat"},
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
            model_id = registry.model_for(spec.name)
            embedding_only = "embed" in model_id.lower()
            providers.append(
                ModelProvider(
                    model_id=model_id,
                    provider=spec.name,
                    roles={"embedding"} if embedding_only else {"planner", "fallback", "chat"},
                    privacy_class="cloud",
                    supports_tools=False,
                    max_concurrency=1,
                    priority=10,
                    availability="online" if registry.is_available(spec.name) else "unavailable",
                    capabilities={"embedding"} if embedding_only else {"chat"},
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
        candidates = self.candidates(
            role=role,
            privacy_class=privacy_class,
            requires_tools=requires_tools,
            preferred_model=preferred_model,
        )
        if not candidates:
            raise ModelUnavailable("no_provider_available")
        return candidates[0]

    def candidates(
        self,
        *,
        role: str,
        privacy_class: str = "local",
        requires_tools: bool = False,
        preferred_model: str | None = None,
        capability: str | None = None,
    ) -> list[ModelProvider]:
        """Return eligible providers in deterministic priority order.

        The caller may use this list to implement a bounded fallback chain.
        Eligibility never grants MCP permissions.
        """
        candidates = list(self.providers.values())
        if preferred_model:
            candidates.sort(key=lambda item: (item.model_id != preferred_model, item.priority))
        else:
            candidates.sort(key=lambda item: item.priority)
        eligible = []
        for item in candidates:
            if role not in item.roles and "general" not in item.roles:
                continue
            if item.availability != "online" or self.circuits[item.model_id].open:
                continue
            if requires_tools and not item.supports_tools:
                continue
            if privacy_class == "local" and item.privacy_class != "local":
                continue
            if capability and capability not in item.capabilities:
                continue
            eligible.append(item)
        return eligible

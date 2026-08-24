from __future__ import annotations

import copy
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    key_names: tuple[str, ...]
    base_url: str
    default_model: str
    model_family: str
    control_authority: bool = False
    account_id_name: str = ''


@dataclass
class ProviderState:
    configured: bool = False
    health: str = 'not_configured'
    disabled_reason: str = ''
    circuit_state: str = 'disabled'
    failures: int = 0
    opened_until: float = 0.0
    latency_ms: float | None = None
    quota_state: str = 'unknown'
    recent_reliability: float = 0.95
    last_checked_at: float = 0.0


class ProviderCallError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name='nvidia',
        label='NVIDIA NIM',
        key_names=('NVIDIA_API_KEY', 'NVAPI_API_KEY'),
        base_url='https://integrate.api.nvidia.com/v1',
        default_model='nvidia/nemotron-3-ultra-550b-a55b',
        model_family='nemotron',
        control_authority=True,
    ),
    ProviderSpec(
        name='gemini',
        label='Google Gemini',
        key_names=('GEMINI_API_KEY',),
        base_url='https://generativelanguage.googleapis.com/v1beta/openai',
        default_model='gemini-3.7-flash',
        model_family='gemini',
    ),
    ProviderSpec(
        name='groq',
        label='Groq',
        key_names=('GROQ_API_KEY',),
        base_url='https://api.groq.com/openai/v1',
        default_model='openai/gpt-oss-120b',
        model_family='gpt-oss',
    ),
    ProviderSpec(
        name='cerebras',
        label='Cerebras',
        key_names=('CEREBRAS_API_KEY',),
        base_url='https://api.cerebras.ai/v1',
        default_model='zai-glm-4.7',
        model_family='glm',
    ),
    ProviderSpec(
        name='openrouter',
        label='OpenRouter Free',
        key_names=('OPENROUTER_API_KEY',),
        base_url='https://openrouter.ai/api/v1',
        default_model='openrouter/free',
        model_family='openrouter-free',
    ),
    ProviderSpec(
        name='cloudflare',
        label='Cloudflare Workers AI',
        key_names=('CLOUDFLARE_API_TOKEN',),
        account_id_name='CLOUDFLARE_ACCOUNT_ID',
        base_url='https://api.cloudflare.com/client/v4/accounts',
        default_model='@cf/meta/llama-3.3-70b-instruct-fp8-fast',
        model_family='llama',
    ),
)


MODEL_OVERRIDES = {
    ('nvidia', 'control'): 'nvidia/nemotron-3-ultra-550b-a55b',
    ('nvidia', 'coding'): 'poolside/laguna-xs-2.1',
    ('nvidia', 'general_backup'): 'z-ai/glm-5.2',
}

NVIDIA_PURPOSE_ENV = {
    'control': 'NVIDIA_CONTROL_MODEL',
    'coding': 'NVIDIA_CODING_MODEL',
    'general_backup': 'NVIDIA_GENERAL_BACKUP_MODEL',
}


def _truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'enabled'}


def _clean_env(env: Mapping[str, Any] | None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {str(key): str(value or '').strip() for key, value in source.items()}


class ProviderRegistry:
    def __init__(
        self,
        *,
        env: Mapping[str, Any] | None = None,
        free_tier_confirmed: Iterable[str] = (),
        now: Callable[[], float] = time.time,
        credential_resolver: Callable[[str], str] | None = None,
    ):
        self._env = _clean_env(env)
        self._now = now
        self._credential_resolver = credential_resolver
        self._specs = {spec.name: spec for spec in PROVIDER_SPECS}
        self._states = {name: ProviderState() for name in self._specs}
        self._credentials: dict[str, str] = {}
        self._accounts: dict[str, str] = {}
        self._models = {name: spec.default_model for name, spec in self._specs.items()}
        self._purpose_models = dict(MODEL_OVERRIDES)
        self._discovered_models: dict[str, set[str]] = {}
        self._confirmed = {str(name).strip().lower() for name in free_tier_confirmed}
        self._configure()
        self._apply_family_diversity()

    def _first_value(self, provider: str, names: tuple[str, ...]) -> str:
        if self._credential_resolver is not None:
            try:
                resolved = str(self._credential_resolver(provider) or '').strip()
            except Exception:
                resolved = ''
            if resolved and not self._is_placeholder(resolved):
                return resolved
        for name in names:
            value = self._env.get(name, '').strip()
            if value and not self._is_placeholder(value):
                return value
        return ''

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        normalized = str(value or '').strip().lower()
        return (
            not normalized
            or normalized.startswith('your_')
            or normalized.endswith('_here')
            or normalized in {'changeme', 'placeholder', 'example'}
        )

    def _is_free_tier_confirmed(self, provider: str) -> bool:
        if provider == 'nvidia':
            return True
        if provider in self._confirmed:
            return True
        env_name = f'TREVOR_{provider.upper()}_FREE_TIER_CONFIRMED'
        return _truthy(self._env.get(env_name, ''))

    def _configure(self) -> None:
        for name, spec in self._specs.items():
            state = self._states[name]
            credential = self._first_value(name, spec.key_names)
            account_id = self._env.get(spec.account_id_name, '').strip() if spec.account_id_name else ''
            if credential:
                self._credentials[name] = credential
            if account_id:
                self._accounts[name] = account_id
            state.configured = bool(credential and (not spec.account_id_name or account_id))
            if not state.configured:
                state.disabled_reason = 'credentials_missing'
                continue

            model_env_name = {
                'nvidia': 'NVIDIA_CONTROL_MODEL',
                'gemini': 'GEMINI_MODEL',
                'groq': 'GROQ_MODEL',
                'cerebras': 'CEREBRAS_MODEL',
                'openrouter': 'OPENROUTER_FREE_MODEL',
                'cloudflare': 'CLOUDFLARE_MODEL',
            }[name]
            requested_model = self._env.get(model_env_name, '').strip()
            if requested_model and not self._is_placeholder(requested_model):
                self._models[name] = requested_model

            if name == 'nvidia':
                for purpose, purpose_env_name in NVIDIA_PURPOSE_ENV.items():
                    purpose_model = self._env.get(purpose_env_name, '').strip()
                    if purpose_model and not self._is_placeholder(purpose_model):
                        self._purpose_models[(name, purpose)] = purpose_model
                self._models[name] = self._purpose_models[(name, 'control')]

            if not self._is_free_tier_confirmed(name):
                state.disabled_reason = 'free_tier_unconfirmed'
                continue
            if name == 'openrouter' and not self._is_free_openrouter_model(self._models[name]):
                state.disabled_reason = 'paid_model_blocked'
                continue
            if name == 'cloudflare' and self._env.get('CLOUDFLARE_PLAN', '').strip().lower() != 'free':
                state.disabled_reason = 'free_plan_required'
                continue
            state.health = 'available'
            state.circuit_state = 'closed'
            state.disabled_reason = ''

    @staticmethod
    def _is_free_openrouter_model(model: str) -> bool:
        normalized = str(model or '').strip().lower()
        return normalized == 'openrouter/free' or normalized.endswith(':free')

    def model_family_for(self, provider: str, purpose: str = 'dialogue') -> str:
        model = self.model_for(provider, purpose).lower()
        for token, family in (
            ('nemotron', 'nemotron'),
            ('laguna', 'laguna'),
            ('gemini', 'gemini'),
            ('gpt-oss', 'gpt-oss'),
            ('glm', 'glm'),
            ('llama', 'llama'),
        ):
            if token in model:
                return family
        return self.get(provider).model_family

    def _apply_family_diversity(self) -> None:
        seen: set[str] = set()
        for name in ('nvidia', 'gemini', 'groq', 'cerebras'):
            state = self._states[name]
            if not state.configured or state.disabled_reason:
                continue
            family = self.model_family_for(name)
            if family in seen:
                state.disabled_reason = 'duplicate_model_family'
                state.health = 'disabled'
                state.circuit_state = 'disabled'
                continue
            seen.add(family)

    def get(self, provider: str) -> ProviderSpec:
        return self._specs[str(provider).strip().lower()]

    def state(self, provider: str) -> ProviderState:
        return self._states[str(provider).strip().lower()]

    def model_for(self, provider: str, purpose: str = 'dialogue') -> str:
        key = (str(provider).strip().lower(), str(purpose).strip().lower())
        return self._purpose_models.get(key, self._models[key[0]])

    def fallback_models_for(self, provider: str, purpose: str = 'dialogue') -> tuple[str, ...]:
        name = str(provider or '').strip().lower()
        requested_purpose = str(purpose or 'dialogue').strip().lower()
        if name != 'nvidia':
            return ()
        candidates = (
            ('control', 'general_backup')
            if requested_purpose == 'coding'
            else ('general_backup',)
        )
        primary = self.model_for(name, requested_purpose)
        fallback_models = []
        for fallback_purpose in candidates:
            model = self.model_for(name, fallback_purpose)
            discovered = self._discovered_models.get(name)
            if discovered is not None and model.removeprefix('models/') not in discovered:
                continue
            if model != primary and model not in fallback_models:
                fallback_models.append(model)
        return tuple(fallback_models)

    def is_available(self, provider: str) -> bool:
        name = str(provider).strip().lower()
        state = self._states[name]
        if state.circuit_state == 'open' and state.opened_until <= self._now():
            state.circuit_state = 'half_open'
            state.disabled_reason = ''
        return bool(
            state.configured
            and not state.disabled_reason
            and state.circuit_state in {'closed', 'half_open'}
        )

    def available(self, providers: Iterable[str]) -> list[str]:
        return [name for name in providers if name in self._specs and self.is_available(name)]

    def validate_models(self, fetcher: Callable[[str], Iterable[str]]) -> None:
        for name in self._specs:
            state = self._states[name]
            if not state.configured or state.disabled_reason not in {'', 'model_unavailable'}:
                continue
            try:
                discovered = {
                    str(model).removeprefix('models/').strip()
                    for model in fetcher(name)
                    if str(model).strip()
                }
            except Exception as exc:
                status_code = getattr(exc, 'status_code', None)
                if status_code in {400, 401, 403}:
                    state.health = 'disabled'
                    state.disabled_reason = 'authentication_failed'
                    state.circuit_state = 'disabled'
                elif status_code == 402:
                    state.health = 'disabled'
                    state.disabled_reason = 'payment_required'
                    state.quota_state = 'blocked'
                    state.circuit_state = 'open'
                elif status_code == 429:
                    state.health = 'disabled'
                    state.disabled_reason = 'quota_exhausted'
                    state.quota_state = 'exhausted'
                    state.circuit_state = 'open'
                else:
                    state.health = 'degraded'
                state.last_checked_at = self._now()
                continue
            state.last_checked_at = self._now()
            self._discovered_models[name] = discovered
            expected = self.model_for(name)
            if discovered and expected.removeprefix('models/') in discovered:
                state.disabled_reason = ''
                state.health = 'available'
                state.circuit_state = 'closed'
            else:
                state.disabled_reason = 'model_unavailable'
                state.health = 'disabled'
                state.circuit_state = 'disabled'

    def record_success(self, provider: str, latency_ms: float | None = None) -> None:
        state = self.state(provider)
        state.failures = 0
        state.health = 'available'
        state.circuit_state = 'closed'
        state.disabled_reason = ''
        state.quota_state = 'available'
        state.latency_ms = latency_ms
        state.recent_reliability = min(1.0, state.recent_reliability * 0.9 + 0.1)

    def record_failure(self, provider: str, status_code: int | None = None) -> None:
        state = self.state(provider)
        state.failures += 1
        state.health = 'degraded'
        state.recent_reliability = max(0.0, state.recent_reliability * 0.8)
        if status_code == 429:
            state.disabled_reason = 'quota_exhausted'
            state.quota_state = 'exhausted'
            state.circuit_state = 'open'
            state.opened_until = self._now() + 900
        elif status_code == 402:
            state.disabled_reason = 'payment_required'
            state.quota_state = 'blocked'
            state.circuit_state = 'open'
            state.opened_until = self._now() + 86400
        elif state.failures >= 3:
            state.disabled_reason = 'circuit_open'
            state.circuit_state = 'open'
            state.opened_until = self._now() + 300

    def build_dialogue_request(
        self,
        provider: str,
        context: Mapping[str, Any],
        *,
        purpose: str = 'dialogue',
    ) -> dict[str, Any]:
        name = str(provider).strip().lower()
        spec = self.get(name)
        capability_boundary = (
            'You are the NVIDIA control core for Trevor. The Trevor runtime may use only '
            'capabilities explicitly listed in trevor_context.runtime_capabilities. This '
            'candidate call does not execute tools directly, so do not invent execution '
            'results. Do not claim that Trevor lacks tools, workspace access, external APIs, '
            'autonomy, or persistent memory when the runtime capability manifest marks them ready.'
            if spec.control_authority
            else
            'You are a read-only external candidate. This candidate seat has no tools, task API, '
            'autonomy API, or memory-write access. Do not generalize this seat limitation to Trevor. '
            'Use trevor_context.runtime_capabilities as the only source of truth about the Trevor runtime.'
        )
        request: dict[str, Any] = {
            'request_type': 'candidate',
            'model': self.model_for(name, purpose),
            'stream': False,
            'temperature': 0.2,
            'response_format': {'type': 'json_object'},
            'trevor_context': copy.deepcopy(dict(context)),
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'Return one JSON object only with answer, claims, evidence, assumptions, confidence, '
                        'and quality. quality must be an object with numeric evidence_verification and '
                        'requirement_fit fields plus boolean safe, privacy_ok, format_ok, and tests_ok fields. '
                        f'Do not reveal hidden reasoning. {capability_boundary}'
                    ),
                },
                {'role': 'user', 'content': copy.deepcopy(dict(context))},
            ],
        }
        if name == 'openrouter':
            request['provider'] = {
                'zdr': True,
                'data_collection': 'deny',
                'allow_fallbacks': False,
                'require_parameters': True,
                'max_price': {'prompt': 0, 'completion': 0},
            }
        return request

    def credential_for(self, provider: str) -> str:
        return self._credentials.get(str(provider).strip().lower(), '')

    def account_for(self, provider: str) -> str:
        return self._accounts.get(str(provider).strip().lower(), '')

    def public_status(self) -> dict[str, Any]:
        providers = []
        for name, spec in self._specs.items():
            state = self._states[name]
            public_reason = (
                'not_configured' if state.disabled_reason == 'credentials_missing' else state.disabled_reason
            )
            providers.append(
                {
                    'provider': name,
                    'label': spec.label,
                    'model': self.model_for(name),
                    'family': self.model_family_for(name),
                    'enabled': self.is_available(name),
                    'health': state.health,
                    'latency_ms': state.latency_ms,
                    'quota': {'state': state.quota_state, 'paid_fallback': False},
                    'circuit': {'state': state.circuit_state},
                    'disabled_reason': public_reason,
                    'free_only': True,
                    'control_authority': spec.control_authority,
                }
            )
        return {'ok': True, 'free_only': True, 'providers': providers}


__all__ = [
    'MODEL_OVERRIDES',
    'PROVIDER_SPECS',
    'ProviderCallError',
    'ProviderRegistry',
    'ProviderSpec',
    'ProviderState',
]

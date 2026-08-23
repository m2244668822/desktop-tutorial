from __future__ import annotations

import json
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from core.provider_registry import ProviderCallError, ProviderRegistry, ProviderSpec


class ProviderHttpClient:
    def __init__(self, registry: ProviderRegistry, *, timeout: float = 45.0):
        self.registry = registry
        self.timeout = max(5.0, float(timeout))

    @staticmethod
    def wire_payload(request: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in dict(request).items()
            if key not in {'trevor_context', 'request_type'}
        }
        messages = []
        for item in payload.get('messages', []):
            if not isinstance(item, Mapping):
                continue
            content = item.get('content', '')
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, sort_keys=True)
            messages.append({'role': str(item.get('role', 'user')), 'content': content})
        payload['messages'] = messages
        return payload

    def endpoint_for(self, provider: str) -> str:
        name = str(provider).strip().lower()
        spec = self.registry.get(name)
        if name == 'cloudflare':
            account = self.registry.account_for(name)
            model = self.registry.model_for(name)
            return f'{spec.base_url}/accounts/{account}/ai/run/{model}'
        return f'{spec.base_url.rstrip("/")}/chat/completions'

    def _headers_for(self, provider: str) -> dict[str, str]:
        name = str(provider).strip().lower()
        token = self.registry.credential_for(name)
        if not token:
            raise ProviderCallError(f'{name}: not configured')
        if name == 'gemini':
            return {'Content-Type': 'application/json', 'x-goog-api-key': token}
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        }

    @staticmethod
    def _extract_content(provider: str, payload: Mapping[str, Any]) -> Any:
        if provider == 'cloudflare':
            result = payload.get('result', {})
            if isinstance(result, Mapping):
                response = result.get('response', result.get('text', ''))
                if response:
                    return response
                payload = result
        choices = payload.get('choices', [])
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], Mapping) else {}
            message = first.get('message', {}) if isinstance(first, Mapping) else {}
            if isinstance(message, Mapping):
                return message.get('content', '')
        return payload.get('response', '')

    def call(self, provider: ProviderSpec, request: dict[str, Any]) -> Any:
        name = provider.name
        if not self.registry.is_available(name):
            raise ProviderCallError(f'{name}: unavailable')
        payload = self.wire_payload(request)
        if name == 'cloudflare':
            payload.pop('model', None)
            payload.pop('provider', None)
            payload.pop('response_format', None)
        encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        http_request = urllib_request.Request(
            self.endpoint_for(name),
            data=encoded,
            headers=self._headers_for(name),
            method='POST',
        )
        try:
            with urllib_request.urlopen(http_request, timeout=self.timeout) as response:
                body = response.read().decode('utf-8', errors='replace')
        except urllib_error.HTTPError as exc:
            raise ProviderCallError(
                f'{name}: HTTP {exc.code}',
                status_code=int(exc.code),
            ) from exc
        except urllib_error.URLError as exc:
            raise ProviderCallError(f'{name}: network unavailable') from exc
        try:
            parsed = json.loads(body or '{}')
        except json.JSONDecodeError as exc:
            raise ProviderCallError(f'{name}: invalid JSON response') from exc
        content = self._extract_content(name, parsed if isinstance(parsed, Mapping) else {})
        if not content:
            raise ProviderCallError(f'{name}: empty response')
        return content

    def list_models(self, provider: str) -> set[str]:
        name = str(provider).strip().lower()
        if name == 'cloudflare':
            return {self.registry.model_for(name)}
        spec = self.registry.get(name)
        endpoint = f'{spec.base_url.rstrip("/")}/models'
        request = urllib_request.Request(endpoint, headers=self._headers_for(name), method='GET')
        try:
            with urllib_request.urlopen(request, timeout=min(self.timeout, 15.0)) as response:
                body = response.read().decode('utf-8', errors='replace')
        except (urllib_error.HTTPError, urllib_error.URLError) as exc:
            raise ProviderCallError(f'{name}: model discovery failed') from exc
        parsed = json.loads(body or '{}')
        rows = parsed.get('data', parsed.get('models', [])) if isinstance(parsed, Mapping) else []
        models = set()
        for item in rows if isinstance(rows, list) else []:
            if isinstance(item, Mapping):
                model = item.get('id', item.get('name', ''))
            else:
                model = item
            if model:
                models.add(str(model).removeprefix('models/'))
        return models


__all__ = ['ProviderHttpClient']

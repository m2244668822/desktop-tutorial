from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse
from pathlib import Path

from core.keychain_credentials import KeychainCredentialStore


ERROR_MESSAGES = {
    'credential_missing': '尚未設定 AI Horde 憑證，請在本機執行 Keychain 設定工具。',
    'credential_unavailable': '目前無法讀取 AI Horde 憑證。',
    'invalid_request': '生成要求格式不正確。',
    'queue_full': '共享算力本機佇列已滿，請稍後重試。',
    'provider_rejected': '共享算力拒絕了這次要求。',
    'provider_rate_limited': '共享算力目前忙碌，請稍後重試。',
    'provider_unavailable': '共享算力目前無法連線，請稍後重試。',
    'job_timeout': '共享算力等待逾時，請稍後重新提交。',
    'asset_fetch_failed': '生成完成，但圖片安全下載失敗。',
    'job_not_found': '工作不存在或已過期，請重新提交。',
}


@dataclass
class AIHordeError(RuntimeError):
    code: str
    retryable: bool = False
    provider_rc: str = field(default='', repr=False)

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, ERROR_MESSAGES.get(self.code, ERROR_MESSAGES['provider_unavailable']))

    def public_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'message': ERROR_MESSAGES.get(self.code, ERROR_MESSAGES['provider_unavailable']),
            'retryable': self.retryable,
        }


def _integer(value: Any, *, minimum: int, maximum: int, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise AIHordeError('invalid_request')
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AIHordeError('invalid_request') from exc
    if result < minimum or result > maximum:
        raise AIHordeError('invalid_request')
    return result


def _number(value: Any, *, minimum: float, maximum: float, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise AIHordeError('invalid_request')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AIHordeError('invalid_request') from exc
    if result < minimum or result > maximum:
        raise AIHordeError('invalid_request')
    return result


def validate_horde_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - {'kind', 'prompt', 'params'}:
        raise AIHordeError('invalid_request')
    kind = str(payload.get('kind', '') or '').strip().lower()
    if kind not in {'image', 'text'}:
        raise AIHordeError('invalid_request')
    prompt = payload.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        raise AIHordeError('invalid_request')
    prompt = prompt.strip()
    if len(prompt) > (4000 if kind == 'image' else 12000):
        raise AIHordeError('invalid_request')
    params = payload.get('params', {})
    if not isinstance(params, dict):
        raise AIHordeError('invalid_request')
    if kind == 'image':
        if set(params) - {'width', 'height', 'steps'}:
            raise AIHordeError('invalid_request')
        width = _integer(params.get('width'), minimum=256, maximum=1024, default=512)
        height = _integer(params.get('height'), minimum=256, maximum=1024, default=512)
        if width % 64 or height % 64:
            raise AIHordeError('invalid_request')
        normalized_params = {
            'width': width,
            'height': height,
            'steps': _integer(params.get('steps'), minimum=1, maximum=50, default=30),
        }
    else:
        if set(params) - {'max_length', 'temperature', 'top_p'}:
            raise AIHordeError('invalid_request')
        normalized_params = {
            'max_length': _integer(
                params.get('max_length'), minimum=32, maximum=1024, default=256
            ),
            'temperature': _number(
                params.get('temperature'), minimum=0, maximum=2, default=0.7
            ),
            'top_p': _number(params.get('top_p'), minimum=0, maximum=1, default=0.9),
        }
    return {'kind': kind, 'prompt': prompt, 'params': normalized_params}


class UrllibJsonTransport:
    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any] | None,
        timeout: float,
    ) -> tuple[int, dict[str, Any]]:
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        request = urllib_request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                raw = response.read(1024 * 1024)
                decoded = json.loads(raw.decode('utf-8')) if raw else {}
                return int(response.status), decoded if isinstance(decoded, dict) else {}
        except urllib_error.HTTPError as exc:
            raw = exc.read(64 * 1024)
            try:
                decoded = json.loads(raw.decode('utf-8')) if raw else {}
            except Exception:
                decoded = {}
            return int(exc.code), decoded if isinstance(decoded, dict) else {}
        except (urllib_error.URLError, TimeoutError, socket.timeout) as exc:
            raise AIHordeError('provider_unavailable', retryable=True) from exc


class AIHordeClient:
    def __init__(
        self,
        *,
        credential_store: KeychainCredentialStore | None = None,
        transport: Any | None = None,
        api_base: str | None = None,
        client_agent: str | None = None,
        keychain_service: str | None = None,
        keychain_account: str | None = None,
        timeout: float | None = None,
        credentials_directory: str | os.PathLike[str] | None = None,
    ):
        self.credential_store = credential_store or KeychainCredentialStore()
        self.transport = transport or UrllibJsonTransport()
        self.api_base = str(
            api_base or os.getenv('AI_HORDE_API_BASE', 'https://stablehorde.net/api')
        ).rstrip('/')
        parsed = urlparse(self.api_base)
        if parsed.scheme != 'https' or parsed.hostname not in {'stablehorde.net', 'aihorde.net'}:
            raise AIHordeError('invalid_request')
        self.client_agent = str(
            client_agent or os.getenv('AI_HORDE_CLIENT_AGENT', 'Trevor:1.0:local-client')
        ).strip()
        self.keychain_service = str(
            keychain_service or os.getenv('AI_HORDE_KEYCHAIN_SERVICE', 'perob.ai-horde')
        ).strip()
        self.keychain_account = str(
            keychain_account or os.getenv('AI_HORDE_KEYCHAIN_ACCOUNT', 'api-key')
        ).strip()
        self.timeout = float(timeout or os.getenv('AI_HORDE_REQUEST_TIMEOUT_SECONDS', '30'))
        self.credentials_directory = (
            Path(credentials_directory).expanduser()
            if credentials_directory is not None
            else None
        )

    def __repr__(self) -> str:
        return f'AIHordeClient(api_base={self.api_base!r}, credential_source="secure_store")'

    def _systemd_credential(self) -> str:
        directory = self.credentials_directory
        if directory is None:
            configured = str(os.getenv('CREDENTIALS_DIRECTORY', '') or '').strip()
            directory = Path(configured) if configured else None
        if directory is None:
            return ''
        try:
            return (directory / 'ai_horde_api_key').read_text(encoding='utf-8').strip()
        except OSError:
            return ''

    def public_status(self) -> dict[str, Any]:
        enabled = str(os.getenv('AI_HORDE_ENABLED', 'true')).strip().lower() in {
            '1',
            'true',
            'yes',
            'on',
        }
        systemd_credential = self._systemd_credential()
        credential = self.credential_store.get_secret(self.keychain_service, self.keychain_account)
        source = 'systemd' if systemd_credential else ('keychain' if credential.configured else 'none')
        return {
            'ok': True,
            'enabled': enabled,
            'configured': bool(systemd_credential or credential.configured),
            'key_source': source,
            'supports': ['image', 'text'],
        }

    def _credential(self) -> str:
        systemd_credential = self._systemd_credential()
        if systemd_credential:
            return systemd_credential
        result = self.credential_store.get_secret(self.keychain_service, self.keychain_account)
        if result.configured:
            return result.value
        code = (
            'credential_missing'
            if result.error_code == 'credential_missing'
            else 'credential_unavailable'
        )
        raise AIHordeError(code)

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Client-Agent': self.client_agent,
            'apikey': self._credential(),
        }
        try:
            status, response = self.transport.request_json(
                method,
                f'{self.api_base}{path}',
                headers=headers,
                payload=payload,
                timeout=self.timeout,
            )
        except AIHordeError:
            raise
        except Exception as exc:
            raise AIHordeError('provider_unavailable', retryable=True) from exc
        if 200 <= int(status) < 300:
            return response if isinstance(response, dict) else {}
        rc = str(response.get('rc', '') if isinstance(response, dict) else '')
        if int(status) == 429 or rc in {'TooManyPrompts', 'KudosUpfront', 'SharedKeyEmpty'}:
            raise AIHordeError('provider_rate_limited', retryable=True, provider_rc=rc)
        if int(status) >= 500 or rc in {'MaintenanceMode', 'NoValidWorkers'}:
            raise AIHordeError('provider_unavailable', retryable=True, provider_rc=rc)
        raise AIHordeError('provider_rejected', provider_rc=rc)

    def submit(self, kind: str, prompt: str, params: dict[str, Any] | None = None) -> str:
        normalized = validate_horde_request(
            {'kind': kind, 'prompt': prompt, 'params': params or {}}
        )
        if normalized['kind'] == 'image':
            payload = {
                'prompt': normalized['prompt'],
                'params': {**normalized['params'], 'n': 1},
                'nsfw': False,
                'censor_nsfw': True,
                'r2': True,
            }
            path = '/v2/generate/async'
        else:
            payload = {'prompt': normalized['prompt'], 'params': normalized['params']}
            path = '/v2/generate/text/async'
        response = self._request('POST', path, payload)
        provider_id = str(response.get('id', '') or '').strip()
        if not provider_id:
            raise AIHordeError('provider_unavailable', retryable=True)
        return provider_id

    def status(self, kind: str, provider_id: str) -> dict[str, Any]:
        safe_id = str(provider_id or '').strip()
        if not safe_id:
            raise AIHordeError('job_not_found')
        if kind == 'image':
            check = self._request('GET', f'/v2/generate/check/{safe_id}')
            if not bool(check.get('done')):
                return check
            return self._request('GET', f'/v2/generate/status/{safe_id}')
        if kind == 'text':
            return self._request('GET', f'/v2/generate/text/status/{safe_id}')
        raise AIHordeError('invalid_request')


__all__ = ['AIHordeClient', 'AIHordeError', 'validate_horde_request']

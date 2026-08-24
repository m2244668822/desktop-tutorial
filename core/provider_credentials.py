from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.keychain_credentials import KeychainCredentialStore


_PROVIDER_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_-]*$')


@dataclass(frozen=True)
class ResolvedProviderCredential:
    configured: bool
    source: str
    value: str = field(default='', repr=False)

    def public_status(self) -> dict[str, Any]:
        return {'configured': self.configured, 'source': self.source}


class ProviderCredentialResolver:
    def __init__(
        self,
        *,
        credential_store: KeychainCredentialStore | None = None,
        credentials_directory: str | os.PathLike[str] | None = None,
        service: str = 'trevor.providers',
    ):
        self.credential_store = credential_store or KeychainCredentialStore()
        self.credentials_directory = (
            Path(credentials_directory).expanduser()
            if credentials_directory is not None
            else None
        )
        self.service = str(service or 'trevor.providers').strip()

    def _systemd_directory(self) -> Path | None:
        if self.credentials_directory is not None:
            return self.credentials_directory
        raw = str(os.getenv('CREDENTIALS_DIRECTORY', '') or '').strip()
        return Path(raw).expanduser() if raw else None

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        normalized = str(provider or '').strip().lower()
        return normalized if _PROVIDER_NAME_PATTERN.fullmatch(normalized) else ''

    def resolve(self, provider: str) -> ResolvedProviderCredential:
        name = self._normalize_provider(provider)
        if not name:
            return ResolvedProviderCredential(False, 'none')

        credentials_directory = self._systemd_directory()
        if credentials_directory is not None:
            credential_path = credentials_directory / f'{name}_api_key'
            try:
                value = credential_path.read_text(encoding='utf-8').strip()
            except OSError:
                value = ''
            if value:
                return ResolvedProviderCredential(True, 'systemd', value=value)
            return ResolvedProviderCredential(False, 'none')

        keychain = self.credential_store.get_secret(self.service, f'{name}-api-key')
        if keychain.configured:
            return ResolvedProviderCredential(True, 'keychain', value=keychain.value)
        return ResolvedProviderCredential(False, 'none')


__all__ = ['ProviderCredentialResolver', 'ResolvedProviderCredential']

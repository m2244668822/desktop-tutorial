from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from core.keychain_credentials import KeychainCredentialStore
from core.user_api_keys import TrevorAPIKeyStore, VALID_SCOPES


AUTH_SERVICE = 'trevor.auth'
AUTH_HMAC_ACCOUNT = 'api-key-hmac'
CLIENT_SERVICE = 'trevor.clients'
LOCAL_ADMIN_ACCOUNT = 'local-admin-api-key'


def _systemd_secret(
    credential_name: str,
    credentials_directory: str | os.PathLike[str] | None,
) -> str:
    directory = credentials_directory
    if directory is None:
        directory = str(os.getenv('CREDENTIALS_DIRECTORY', '') or '').strip()
    if not directory:
        return ''
    try:
        return (Path(directory).expanduser() / credential_name).read_text(
            encoding='utf-8'
        ).strip()
    except OSError:
        return ''


def build_api_key_store(
    data_root: str | Path,
    *,
    credentials_directory: str | os.PathLike[str] | None = None,
    credential_store: KeychainCredentialStore | None = None,
) -> tuple[TrevorAPIKeyStore | None, dict[str, Any]]:
    hmac_secret = _systemd_secret('trevor_api_hmac', credentials_directory)
    source = 'systemd' if hmac_secret else 'none'
    store = credential_store or KeychainCredentialStore()
    if not hmac_secret:
        keychain = store.get_secret(AUTH_SERVICE, AUTH_HMAC_ACCOUNT)
        if keychain.configured:
            hmac_secret = keychain.value
            source = 'keychain'
    if len(hmac_secret.encode('utf-8')) < 32:
        return None, {'configured': False, 'source': 'none'}
    key_store = TrevorAPIKeyStore(
        Path(data_root) / 'auth' / 'api_keys.json',
        hmac_secret=hmac_secret,
    )
    return key_store, {'configured': True, 'source': source}


def bootstrap_local_admin(
    data_root: str | Path,
    *,
    credential_store: KeychainCredentialStore | None = None,
) -> dict[str, Any]:
    store = credential_store or KeychainCredentialStore()
    hmac_secret = store.get_secret(AUTH_SERVICE, AUTH_HMAC_ACCOUNT)
    if not hmac_secret.configured:
        created_hmac = store.set_secret(
            AUTH_SERVICE,
            AUTH_HMAC_ACCOUNT,
            secrets.token_urlsafe(32),
        )
        if not created_hmac.configured:
            raise RuntimeError('api_hmac_keychain_unavailable')
    key_store, status = build_api_key_store(data_root, credential_store=store)
    if key_store is None:
        raise RuntimeError('api_hmac_unavailable')

    current = store.get_secret(CLIENT_SERVICE, LOCAL_ADMIN_ACCOUNT)
    if current.configured:
        authorization = key_store.authenticate(current.value, required_scope='users')
        if authorization.get('ok'):
            return {
                'ok': True,
                'created': False,
                'auth': status,
                'key_id': authorization.get('key_id', ''),
                'prefix': authorization.get('prefix', ''),
            }

    created = key_store.create('local-admin', VALID_SCOPES)
    saved = store.set_secret(CLIENT_SERVICE, LOCAL_ADMIN_ACCOUNT, created['api_key'])
    if not saved.configured:
        key_store.revoke(created['record']['id'])
        raise RuntimeError('local_admin_keychain_unavailable')
    return {
        'ok': True,
        'created': True,
        'auth': status,
        'key_id': created['record']['id'],
        'prefix': created['record']['prefix'],
    }


__all__ = [
    'AUTH_HMAC_ACCOUNT',
    'AUTH_SERVICE',
    'CLIENT_SERVICE',
    'LOCAL_ADMIN_ACCOUNT',
    'bootstrap_local_admin',
    'build_api_key_store',
]

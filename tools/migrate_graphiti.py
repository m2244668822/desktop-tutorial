#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graphiti_migration import GraphitiMigrationRunner
from core.audit_chain import HashChainAuditLog
from core.keychain_credentials import KeychainCredentialStore
from tools.agent_memory_manager import AgentMemoryManager


def _credential(name: str, env_name: str) -> str:
    credential_dir = str(os.getenv('CREDENTIALS_DIRECTORY', '') or '').strip()
    if credential_dir:
        try:
            value = (Path(credential_dir) / name).read_text(encoding='utf-8').strip()
        except OSError:
            value = ''
        if value:
            return value
    environment_value = str(os.getenv(env_name, '') or '').strip()
    if environment_value:
        return environment_value
    if str(os.getenv('TREVOR_DISABLE_KEYCHAIN', '') or '').strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }:
        return ''
    account = name.replace('_', '-')
    keychain = KeychainCredentialStore().get_secret('trevor.providers', account)
    if keychain.configured:
        return keychain.value
    return ''


def _sender(base_url: str, token: str):
    endpoint = f"{base_url.rstrip('/')}/v1/episodes"

    def send(payload: dict) -> None:
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        request = urllib_request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            method='POST',
        )
        try:
            with urllib_request.urlopen(request, timeout=120) as response:
                if response.status != 200:
                    raise RuntimeError('graphiti_migration_rejected')
        except (urllib_error.URLError, TimeoutError) as exc:
            raise RuntimeError('graphiti_sidecar_unavailable') from exc

    return send


def main() -> int:
    parser = argparse.ArgumentParser(description='Migrate unified Trevor memory to Graphiti')
    parser.add_argument('--base-url', default='http://127.0.0.1:8091')
    args = parser.parse_args()
    manager = AgentMemoryManager(auto_save=False)
    manifest = manager.memory_dir.parent / 'migrations' / 'graphiti_manifest.json'
    token = _credential('graphiti_token', 'TREVOR_GRAPHITI_TOKEN')
    runner = GraphitiMigrationRunner(
        manifest,
        sender=_sender(args.base_url, token),
        audit_log=HashChainAuditLog(manager.memory_dir.parent / 'audit' / 'events.jsonl'),
    )
    result = runner.run(manager._conversations)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

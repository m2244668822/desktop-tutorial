#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.keychain_credentials import KeychainCredentialStore


SERVICE = 'trevor.providers'
_ASSIGNMENT = re.compile(r'^(?P<prefix>\s*(?:export\s+)?)(?P<name>[A-Z0-9_]+)=(?P<value>.*)$')
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('nvidia', ('NVIDIA_API_KEY', 'NVAPI_API_KEY')),
    ('gemini', ('GEMINI_API_KEY',)),
    ('google', ('GOOGLE_API_KEY',)),
    ('groq', ('GROQ_API_KEY',)),
    ('cerebras', ('CEREBRAS_API_KEY',)),
    ('openrouter', ('OPENROUTER_API_KEY', 'OPENROUTER_API_KEY_2')),
    ('cloudflare', ('CLOUDFLARE_API_TOKEN',)),
)
_ENV_TO_GROUP = {
    env_name: group_name
    for group_name, env_names in _GROUPS
    for env_name in env_names
}


def _unquote(value: str) -> str:
    stripped = str(value or '').strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1].strip()
    return stripped


def _is_real_secret(value: str) -> bool:
    normalized = _unquote(value).lower()
    return bool(
        normalized
        and not normalized.startswith('your_')
        and not normalized.endswith('_here')
        and normalized not in {'changeme', 'placeholder', 'example'}
        and 'placeholder' not in normalized
    )


def _atomic_rewrite(path: Path, lines: list[str]) -> None:
    temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with temporary.open('w', encoding='utf-8', newline='') as file_handle:
        file_handle.writelines(lines)
        file_handle.flush()
        os.fsync(file_handle.fileno())
    os.chmod(temporary, min(mode or 0o600, 0o600))
    os.replace(temporary, path)


def migrate_env_file(
    path: str | Path,
    *,
    credential_store: KeychainCredentialStore | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    env_path = Path(path)
    if not env_path.exists():
        return {'ok': True, 'path': str(env_path), 'migrated': [], 'missing': True}

    lines = env_path.read_text(encoding='utf-8').splitlines(keepends=True)
    discovered: dict[str, list[tuple[str, str]]] = {}
    for line in lines:
        match = _ASSIGNMENT.match(line.rstrip('\r\n'))
        if not match:
            continue
        env_name = match.group('name')
        group_name = _ENV_TO_GROUP.get(env_name)
        value = _unquote(match.group('value'))
        if group_name and _is_real_secret(value):
            discovered.setdefault(group_name, []).append((env_name, value))

    conflicts = sorted(
        group_name
        for group_name, entries in discovered.items()
        if len({value for _, value in entries}) > 1
    )
    if conflicts:
        return {
            'ok': False,
            'path': str(env_path),
            'migrated': [],
            'error': 'credential_conflict',
            'conflicts': conflicts,
        }

    planned = sorted(discovered)
    if not apply or not planned:
        return {'ok': True, 'path': str(env_path), 'migrated': planned, 'applied': False}

    store = credential_store or KeychainCredentialStore()
    for group_name in planned:
        value = discovered[group_name][0][1]
        result = store.set_secret(SERVICE, f'{group_name}-api-key', value)
        if not result.configured:
            return {
                'ok': False,
                'path': str(env_path),
                'migrated': [],
                'error': result.error_code or 'credential_write_failed',
                'provider': group_name,
            }
        verified = store.get_secret(SERVICE, f'{group_name}-api-key')
        if not verified.configured or verified.value != value:
            return {
                'ok': False,
                'path': str(env_path),
                'migrated': [],
                'error': 'credential_verification_failed',
                'provider': group_name,
            }

    scrubbed_lines: list[str] = []
    for line in lines:
        newline = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        match = _ASSIGNMENT.match(line.rstrip('\r\n'))
        if not match:
            scrubbed_lines.append(line)
            continue
        env_name = match.group('name')
        group_name = _ENV_TO_GROUP.get(env_name)
        if group_name in discovered and _is_real_secret(match.group('value')):
            scrubbed_lines.append(f"{match.group('prefix')}{env_name}={newline}")
        else:
            scrubbed_lines.append(line)
    _atomic_rewrite(env_path, scrubbed_lines)
    return {'ok': True, 'path': str(env_path), 'migrated': planned, 'applied': True}


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Move provider API keys from ignored env files to the macOS Keychain'
    )
    parser.add_argument('paths', nargs='*', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    paths = args.paths or [ROOT / '.env', ROOT / '.env.oci', ROOT / '500/llama32-chat/.env']
    results = [migrate_env_file(path, apply=args.apply) for path in paths]
    print(json.dumps({'ok': all(item['ok'] for item in results), 'results': results}, ensure_ascii=False))
    return 0 if all(item['ok'] for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())

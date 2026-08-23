#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api_auth import bootstrap_local_admin
from core.audit_chain import HashChainAuditLog
from core.data_paths import resolve_data_root


def main() -> int:
    data_root = resolve_data_root(ROOT)
    try:
        result = bootstrap_local_admin(data_root)
        HashChainAuditLog(data_root / 'audit' / 'events.jsonl').append(
            'user_key_bootstrap',
            {
                'key_id': result.get('key_id', ''),
                'prefix': result.get('prefix', ''),
                'created': result.get('created', False),
                'scopes': ['chat', 'memory', 'tasks', 'git', 'users', 'audit'],
            },
        )
    except RuntimeError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

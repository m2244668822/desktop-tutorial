#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_paths import resolve_data_root
from core.release_operations import AUDITED_OPERATION_EVENTS, record_operation, revert_commit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Trevor audited release operations')
    subparsers = parser.add_subparsers(dest='command', required=True)

    audit = subparsers.add_parser('audit')
    audit.add_argument('--event', required=True, choices=sorted(AUDITED_OPERATION_EVENTS))
    audit.add_argument('--status', required=True)
    audit.add_argument('--subject', default='')
    audit.add_argument('--details-json', default='{}')
    audit.add_argument('--data-root', default='')

    rollback = subparsers.add_parser('rollback')
    rollback.add_argument('--commit', required=True)
    rollback.add_argument('--reason', required=True)
    rollback.add_argument('--repository', default=str(ROOT))
    rollback.add_argument('--data-root', default='')
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    data_root = (
        Path(arguments.data_root).expanduser().resolve()
        if arguments.data_root
        else resolve_data_root(ROOT)
    )
    try:
        if arguments.command == 'audit':
            details = json.loads(arguments.details_json)
            if not isinstance(details, dict):
                raise ValueError('details_json_must_be_object')
            event = record_operation(
                data_root,
                arguments.event,
                status=arguments.status,
                subject=arguments.subject,
                details=details,
            )
            result = {
                'ok': True,
                'event_id': event['event_id'],
                'event_hash': event['event_hash'],
            }
        else:
            result = {
                'ok': True,
                **revert_commit(
                    arguments.repository,
                    arguments.commit,
                    data_root=data_root,
                    reason=arguments.reason,
                ),
            }
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

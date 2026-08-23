#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.autonomy import AutonomyPolicy, AutonomyQueue
from core.data_paths import resolve_data_root
from core.trevor_identity import CAPABILITY_MODES, normalize_trevor_identity


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Queue a Trevor autonomy task')
    parser.add_argument('--input', required=True, help='Task instruction')
    parser.add_argument('--capability-mode', choices=CAPABILITY_MODES, default='')
    parser.add_argument('--route', default='', help='Deprecated legacy role alias')
    parser.add_argument(
        '--category',
        choices=sorted(AutonomyPolicy.ALLOWED_CATEGORIES),
        default='maintenance',
    )
    parser.add_argument('--priority', type=int, default=5)
    return parser.parse_args(argv)


def enqueue_task(args: argparse.Namespace, data_root: str | Path) -> dict:
    identity = normalize_trevor_identity(
        role=str(args.route or ''), capability_mode=str(args.capability_mode or '')
    )
    queue = AutonomyQueue(Path(data_root) / 'autonomy' / 'task_queue.json')
    return queue.enqueue(
        str(args.input),
        capability_mode=identity.capability_mode,
        category=str(args.category),
        priority=int(args.priority),
        metadata={
            'legacy_alias_normalized': bool(identity.deprecated_alias),
            'schema_version': identity.schema_version,
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    task = enqueue_task(args, resolve_data_root(ROOT))
    print(
        f"queued {task['id']} agent=trevor capability={task['capability_mode']} "
        f"category={task['category']} priority={task['priority']}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

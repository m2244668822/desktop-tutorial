#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_paths import resolve_data_root
from core.integration_promotion import TrevorIntegrationPromoter


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Promote clean Trevor integration through required CI and auto-merge'
    )
    parser.add_argument('--title', default='Trevor integration')
    parser.add_argument(
        '--body',
        default='Automated Trevor integration promotion guarded by required CI.',
    )
    args = parser.parse_args()
    try:
        result = TrevorIntegrationPromoter(
            ROOT,
            resolve_data_root(ROOT),
        ).promote(title=args.title, body=args.body)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

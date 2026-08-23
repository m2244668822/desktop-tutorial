#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.secret_scanner import SecretScanner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Scan repository files for embedded secrets')
    parser.add_argument('--json', action='store_true', help='Emit redacted JSON output')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = SecretScanner(ROOT).scan_repository()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result['ok']:
        print(f"secret scan passed ({result['scanned_files']} files)")
    else:
        for finding in result['findings']:
            print(
                f"{finding['path']}:{finding['line']}: {finding['rule']} "
                f"[{finding['fingerprint']}]"
            )
        print(f"secret scan failed ({len(result['findings'])} findings)")
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

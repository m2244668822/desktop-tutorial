#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='啟動崔佛前後端服務')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5001)
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--run-health', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = [
        sys.executable,
        str(BASE_DIR / 'system_main.py'),
        'web',
        '--host',
        args.host,
        '--port',
        str(args.port),
        '--energy-lite',
    ]
    if args.open_browser:
        command.append('--open-browser')
    if not args.run_health:
        command.append('--skip-health')
    print(f'啟動崔佛前後端：http://{args.host}:{args.port}')
    try:
        return subprocess.run(command, cwd=BASE_DIR, check=False).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())

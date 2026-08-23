#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]


def _private_tailscale_url(value: str) -> str:
    remote = str(value or '').strip().rstrip('/')
    parsed = urlparse(remote)
    hostname = str(parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'} or not hostname or parsed.path not in {'', '/'}:
        raise ValueError('invalid_edge_remote_url')
    allowed = hostname in {'localhost'} or hostname.endswith('.ts.net') or '.' not in hostname
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        tailnet = ipaddress.ip_network('100.64.0.0/10')
        allowed = address.is_loopback or address.is_private or address in tailnet
    if not allowed:
        raise ValueError('edge_remote_must_be_private_tailscale')
    return remote


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Install Trevor macOS Edge LaunchAgent')
    parser.add_argument(
        '--remote-url',
        default=os.getenv('TREVOR_EDGE_REMOTE_URL', ''),
        required=not bool(os.getenv('TREVOR_EDGE_REMOTE_URL', '').strip()),
    )
    parser.add_argument('--no-load', action='store_true')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    remote_url = _private_tailscale_url(args.remote_url)
    data_root = Path.home() / 'Library' / 'Application Support' / 'Trevor'
    log_root = Path.home() / 'Library' / 'Logs' / 'Trevor'
    log_root.mkdir(parents=True, exist_ok=True)
    template = (ROOT / 'deploy' / 'launchd' / 'com.trevor.edge.plist').read_text(
        encoding='utf-8'
    )
    replacements = {
        '__TREVOR_PYTHON__': str(Path(sys.executable).resolve()),
        '__TREVOR_ROOT__': str(ROOT),
        '__TREVOR_DATA_DIR__': str(data_root),
        '__TREVOR_LOG_DIR__': str(log_root),
        '__TREVOR_REMOTE_URL__': remote_url,
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, escape(value))
    plistlib.loads(rendered.encode('utf-8'))

    target = Path.home() / 'Library' / 'LaunchAgents' / 'com.trevor.edge.plist'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.tmp-{os.getpid()}')
    temporary.write_text(rendered, encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    if not args.no_load:
        domain = f'gui/{os.getuid()}'
        subprocess.run(['launchctl', 'bootout', domain, str(target)], check=False)
        subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
    print(f'installed {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


def tailscale_status(
    *,
    system_name: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    values = os.environ if env is None else env
    system = str(system_name or platform.system()).strip().lower()
    configured_hint = bool(str(values.get('TAILSCALE_HOSTNAME', '') or '').strip())
    if system == 'darwin':
        try:
            result = runner(
                ['/usr/sbin/scutil', '--nc', 'status', 'Tailscale'],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            state = str(result.stdout or '').splitlines()[0].strip().lower()
            if result.returncode == 0 and state in {'connected', 'connecting', 'disconnected'}:
                return {
                    'configured': True,
                    'connected': state == 'connected',
                }
        except (OSError, subprocess.SubprocessError, IndexError):
            pass

    socket_configured = any(
        path.exists()
        for path in (
            Path('/var/run/tailscale/tailscaled.sock'),
            Path('/var/run/tailscaled.sock'),
        )
    )
    executable = shutil.which('tailscale')
    if executable:
        try:
            result = runner(
                [executable, 'status', '--json'],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            payload = json.loads(result.stdout or '{}') if result.returncode == 0 else {}
            backend_state = str(payload.get('BackendState', '') or '').strip().lower()
            if backend_state:
                return {
                    'configured': True,
                    'connected': backend_state == 'running',
                }
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            pass
    return {
        'configured': bool(configured_hint or socket_configured),
        'connected': False,
    }


__all__ = ['tailscale_status']

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Sequence
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.trevor.autonomy"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_paths import resolve_data_root


def normalize_executable_path(value: str | Path) -> Path:
    return Path(value).expanduser().absolute()


def _default_python() -> Path:
    candidate = ROOT / ".venv312" / "bin" / "python"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return normalize_executable_path(candidate)
    return normalize_executable_path(sys.executable)


def render_launchagent(
    *,
    root: Path,
    python_executable: Path,
    data_root: Path,
    log_root: Path,
) -> str:
    template = (root / "deploy" / "launchd" / f"{LABEL}.plist").read_text(
        encoding="utf-8"
    )
    replacements = {
        "__TREVOR_PYTHON__": str(python_executable),
        "__TREVOR_ROOT__": str(root),
        "__TREVOR_DATA_DIR__": str(data_root),
        "__TREVOR_LOG_DIR__": str(log_root),
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, escape(value))
    plistlib.loads(rendered.encode("utf-8"))
    return rendered


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Trevor macOS autonomy LaunchAgent"
    )
    parser.add_argument("--python", default=str(_default_python()))
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--no-load", action="store_true")
    return parser.parse_args(argv)


def reload_launchagent(
    target: Path,
    *,
    uid: int | None = None,
    runner: Callable[..., Any] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    domain = f"gui/{os.getuid() if uid is None else uid}"
    service = f"{domain}/{LABEL}"
    runner(
        ["launchctl", "bootout", service],
        check=False,
        capture_output=True,
        text=True,
    )
    for _attempt in range(20):
        result = runner(
            ["launchctl", "print", service],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            break
        sleeper(0.1)

    last_result = None
    for attempt in range(5):
        last_result = runner(
            ["launchctl", "bootstrap", domain, str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if last_result.returncode == 0:
            return
        if attempt < 4:
            sleeper(0.5)
    detail = str(last_result.stderr or last_result.stdout or "").strip()[:500]
    raise RuntimeError(
        f"launchagent_bootstrap_failed:{last_result.returncode}:{detail}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    python_executable = normalize_executable_path(args.python)
    if not python_executable.is_file() or not os.access(python_executable, os.X_OK):
        raise SystemExit("trevor_python_not_executable")

    data_root = (
        Path(args.data_dir).expanduser().resolve()
        if str(args.data_dir).strip()
        else resolve_data_root(ROOT)
    )
    log_root = Path.home() / "Library" / "Logs" / "Trevor"
    log_root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    rendered = render_launchagent(
        root=ROOT,
        python_executable=python_executable,
        data_root=data_root,
        log_root=log_root,
    )

    target = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temporary.write_text(rendered, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)

    stale_pid = data_root / "runtime" / "autonomy.pid"
    stale_pid.unlink(missing_ok=True)
    if not args.no_load:
        reload_launchagent(target)
    print(f"installed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

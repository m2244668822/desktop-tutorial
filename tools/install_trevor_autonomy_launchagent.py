#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import plistlib
import stat
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


def validate_private_credential_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    try:
        root_stat = root.stat()
    except OSError as exc:
        raise RuntimeError("credential_directory_unavailable") from exc
    if not root.is_dir() or stat.S_IMODE(root_stat.st_mode) & 0o077:
        raise RuntimeError("credential_directory_permissions")
    if hasattr(os, "getuid") and root_stat.st_uid != os.getuid():
        raise RuntimeError("credential_directory_owner")
    for name in ("nvidia_api_key", "trevor_memory_key_b64"):
        path = root / name
        try:
            path_stat = path.stat()
        except OSError as exc:
            raise RuntimeError(f"required_runtime_credential_missing:{name}") from exc
        if path.is_symlink() or not path.is_file() or path_stat.st_size <= 0:
            raise RuntimeError(f"required_runtime_credential_missing:{name}")
        if stat.S_IMODE(path_stat.st_mode) & 0o077:
            raise RuntimeError("credential_file_permissions")
        if hasattr(os, "getuid") and path_stat.st_uid != os.getuid():
            raise RuntimeError("credential_file_owner")
    return root


def ensure_data_root_alignment(requested: Path, canonical: Path) -> None:
    if requested.expanduser().resolve() != canonical.expanduser().resolve():
        raise RuntimeError("custom_data_dir_requires_backend_alignment")


def is_external_volume(path: str | Path) -> bool:
    return str(Path(path).expanduser().absolute()).startswith("/Volumes/")


def validate_runtime(python_executable: Path, root: Path) -> None:
    result = subprocess.run(
        [
            str(python_executable),
            "-c",
            "import core.autonomy, core.autonomy_runner, core.workflow_runtime",
        ],
        cwd=str(root),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("trevor_runtime_profile_required")


def render_launchagent(
    *,
    root: Path,
    python_executable: Path,
    data_root: Path,
    log_root: Path,
    credential_root: Path,
) -> str:
    template = (root / "deploy" / "launchd" / f"{LABEL}.plist").read_text(
        encoding="utf-8"
    )
    replacements = {
        "__TREVOR_PYTHON__": str(python_executable),
        "__TREVOR_ROOT__": str(root),
        "__TREVOR_DATA_DIR__": str(data_root),
        "__TREVOR_LOG_DIR__": str(log_root),
        "__TREVOR_CREDENTIAL_DIR__": str(credential_root),
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
    parser.add_argument(
        "--credential-dir",
        default=str(Path.home() / "Library" / "Application Support" / "Trevor" / "credentials"),
    )
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
    validate_runtime(python_executable, ROOT)

    canonical_data_root = resolve_data_root(ROOT)
    data_root = (
        Path(args.data_dir).expanduser().resolve()
        if str(args.data_dir).strip()
        else canonical_data_root
    )
    ensure_data_root_alignment(data_root, canonical_data_root)
    credential_root = validate_private_credential_root(args.credential_dir)
    log_root = Path.home() / "Library" / "Logs" / "Trevor"
    log_root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    rendered = render_launchagent(
        root=ROOT,
        python_executable=python_executable,
        data_root=data_root,
        log_root=log_root,
        credential_root=credential_root,
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
        if is_external_volume(ROOT):
            environment = os.environ.copy()
            environment["TREVOR_DATA_DIR"] = str(data_root)
            environment["TREVOR_CREDENTIAL_SOURCE_DIR"] = str(credential_root)
            subprocess.run(
                [str(ROOT / "tools" / "manage_trevor_autonomy.sh"), "restart"],
                cwd=str(ROOT),
                env=environment,
                check=True,
            )
        else:
            reload_launchagent(target)
    print(f"installed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "runtime_dependency_doctor_latest.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class Probe:
    name: str
    ok: bool
    status: str
    detail: dict[str, Any]
    remediation: dict[str, Any]


RunCommand = Callable[[list[str], int], dict[str, Any]]
WhichCommand = Callable[[str], str | None]


def run_command(cmd: list[str], timeout: int = 8) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {"returncode": 1, "stdout": "", "stderr": "", "error": str(exc)}


def _action(
    summary: str,
    *,
    windows: list[str],
    macos: list[str],
    verify: str,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "windows": windows,
        "macos": macos,
        "verify": verify,
    }


def _clean_env_path(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _has_path_separator(value: str) -> bool:
    return any(sep and sep in value for sep in (os.sep, os.altsep, "/", "\\"))


def _resolve_binary(
    name: str,
    *,
    env_keys: tuple[str, ...] = (),
    env: dict[str, str] | os._Environ[str] = os.environ,
    which: WhichCommand = shutil.which,
) -> dict[str, Any]:
    env_checks: list[dict[str, Any]] = []
    for key in env_keys:
        raw = _clean_env_path(str(env.get(key, "") or ""))
        if not raw:
            env_checks.append({"key": key, "value": "", "configured": False})
            continue
        if _has_path_separator(raw) or Path(raw).is_absolute():
            candidate = Path(raw).expanduser()
            exists = candidate.exists()
            is_file = candidate.is_file()
            env_checks.append(
                {
                    "key": key,
                    "value": raw,
                    "configured": True,
                    "exists": exists,
                    "is_file": is_file,
                }
            )
            if exists and is_file:
                return {
                    "found": True,
                    "source": key,
                    "path": str(candidate),
                    "configured_path": raw,
                    "env_checks": env_checks,
                    "path_lookup": which(name) or "",
                }
            return {
                "found": False,
                "source": key,
                "path": "",
                "configured_path": raw,
                "env_checks": env_checks,
                "path_lookup": which(name) or "",
                "error": "configured_path_not_found",
            }
        resolved = which(raw)
        env_checks.append(
            {
                "key": key,
                "value": raw,
                "configured": True,
                "exists": bool(resolved),
                "is_file": bool(resolved),
            }
        )
        if resolved:
            return {
                "found": True,
                "source": key,
                "path": resolved,
                "configured_path": raw,
                "env_checks": env_checks,
                "path_lookup": which(name) or "",
            }
        return {
            "found": False,
            "source": key,
            "path": "",
            "configured_path": raw,
            "env_checks": env_checks,
            "path_lookup": which(name) or "",
            "error": "configured_command_not_found",
        }

    found = which(name)
    return {
        "found": bool(found),
        "source": "PATH" if found else "missing",
        "path": found or "",
        "configured_path": "",
        "env_checks": env_checks,
        "path_lookup": found or "",
    }


def _version_probe(
    name: str,
    version_args: list[str],
    *,
    env_keys: tuple[str, ...] = (),
    env: dict[str, str] | os._Environ[str] = os.environ,
    runner: RunCommand = run_command,
    which: WhichCommand = shutil.which,
    timeout: int = 8,
    remediation: dict[str, Any],
) -> Probe:
    resolved = _resolve_binary(name, env_keys=env_keys, env=env, which=which)
    detail: dict[str, Any] = {"resolution": resolved}
    if not resolved["found"]:
        return Probe(name, False, str(resolved.get("error") or "missing"), detail, remediation)

    cmd = [str(resolved["path"]), *version_args]
    version = runner(cmd, timeout)
    detail["version_check"] = {
        "command": cmd,
        "returncode": version.get("returncode"),
        "stdout": str(version.get("stdout") or "")[:500],
        "stderr": str(version.get("stderr") or "")[:500],
        "error": version.get("error") or "",
    }
    ok = int(version.get("returncode") or 0) == 0
    return Probe(name, ok, "ready" if ok else "version_failed", detail, remediation)


def _path_entries(env: dict[str, str] | os._Environ[str]) -> dict[str, Any]:
    raw = str(env.get("PATH") or env.get("Path") or "")
    entries = [item for item in raw.split(os.pathsep) if item]
    checked = []
    missing = 0
    for entry in entries[:50]:
        exists = Path(entry).exists()
        if not exists:
            missing += 1
        checked.append({"path": entry, "exists": exists})
    return {
        "count": len(entries),
        "checked_first": checked,
        "missing_in_checked_first": missing,
    }


def probe_shell_context(
    root: Path = ROOT,
    *,
    env: dict[str, str] | os._Environ[str] = os.environ,
    system_name: str | None = None,
) -> Probe:
    system_name = system_name or platform.system()
    env_paths: dict[str, dict[str, Any]] = {}
    for key in ("PWD", "OLDPWD", "CODEX_WORKSPACE", "WORKSPACE", "GITHUB_WORKSPACE"):
        raw = str(env.get(key) or "")
        if not raw:
            continue
        try:
            path = Path(_clean_env_path(raw)).expanduser()
            env_paths[key] = {"value": raw, "exists": path.exists()}
        except Exception as exc:  # noqa: BLE001
            env_paths[key] = {"value": raw, "exists": False, "error": str(exc)}
    stale = {
        key: value
        for key, value in env_paths.items()
        if value.get("value") and not value.get("exists")
    }
    ok = root.exists() and not stale
    return Probe(
        "shell_context",
        ok,
        "ready" if ok else "stale_env_paths",
        {
            "platform": system_name,
            "cwd": str(Path.cwd()),
            "root": str(root),
            "root_exists": root.exists(),
            "shell": env.get("SHELL") or env.get("ComSpec") or "",
            "env_paths": env_paths,
            "path_entries": _path_entries(env),
        },
        _action(
            "Fix stale workspace or PATH entries before debugging runtime services.",
            windows=[
                f"Set-Location '{root}'",
                "git rev-parse --show-toplevel",
                "$env:Path -split ';' | Where-Object { -not (Test-Path $_) }",
            ],
            macos=[
                f"cd '{root}'",
                "git rev-parse --show-toplevel",
                'printf "%s\\n" ${PATH//:/\\n} | while read p; do [ -d "$p" ] || echo "$p"; done',
            ],
            verify="runtime_dependency_doctor shell_context should report ready.",
        ),
    )


def probe_project_python(
    root: Path = ROOT,
    *,
    system_name: str | None = None,
    runner: RunCommand = run_command,
) -> Probe:
    system_name = system_name or platform.system()
    venv_python = (
        root / ".venv" / "Scripts" / "python.exe"
        if system_name == "Windows"
        else root / ".venv" / "bin" / "python"
    )
    current = {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "version_info": list(sys.version_info[:3]),
    }
    detail: dict[str, Any] = {
        "current": current,
        "venv_python": str(venv_python),
        "venv_exists": venv_python.exists(),
    }
    ok = tuple(sys.version_info[:2]) >= (3, 10) and venv_python.exists()
    if venv_python.exists():
        version = runner([str(venv_python), "--version"], 8)
        detail["venv_version_check"] = version
        ok = ok and int(version.get("returncode") or 0) == 0
    return Probe(
        "project_python",
        ok,
        "ready" if ok else "venv_missing_or_unusable",
        detail,
        _action(
            "Create or repair the project Python virtual environment.",
            windows=["py -3.12 -m venv .venv", ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"],
            macos=["python3.12 -m venv .venv", ".venv/bin/python -m pip install -r requirements.txt"],
            verify="Project venv Python should exist and return --version.",
        ),
    )


def probe_node(
    *,
    env: dict[str, str] | os._Environ[str] = os.environ,
    runner: RunCommand = run_command,
    which: WhichCommand = shutil.which,
) -> Probe:
    return _version_probe(
        "node",
        ["--version"],
        env=env,
        runner=runner,
        which=which,
        remediation=_action(
            "Install or expose Node.js before starting n8n.",
            windows=["winget install OpenJS.NodeJS.LTS", "where node"],
            macos=["brew install node", "which node"],
            verify="node --version should return successfully.",
        ),
    )


def probe_n8n_cli(
    *,
    env: dict[str, str] | os._Environ[str] = os.environ,
    runner: RunCommand = run_command,
    which: WhichCommand = shutil.which,
) -> Probe:
    return _version_probe(
        "n8n",
        ["--version"],
        env=env,
        runner=runner,
        which=which,
        timeout=12,
        remediation=_action(
            "Install or expose n8n CLI before relying on workflow imports.",
            windows=["npm install -g n8n", "where n8n"],
            macos=["npm install -g n8n", "which n8n"],
            verify="n8n --version should return successfully.",
        ),
    )


def probe_ffmpeg(
    *,
    env: dict[str, str] | os._Environ[str] = os.environ,
    runner: RunCommand = run_command,
    which: WhichCommand = shutil.which,
) -> Probe:
    return _version_probe(
        "ffmpeg",
        ["-version"],
        env_keys=("FFMPEG_PATH", "XIAOBIAN_FFMPEG_PATH"),
        env=env,
        runner=runner,
        which=which,
        remediation=_action(
            "Install FFmpeg or set a valid FFmpeg path override for n8n Execute Command nodes.",
            windows=[
                "winget install Gyan.FFmpeg",
                "where ffmpeg",
                "$env:FFMPEG_PATH='C:\\path\\to\\ffmpeg.exe'",
            ],
            macos=[
                "brew install ffmpeg",
                "which ffmpeg",
                "export FFMPEG_PATH=/path/to/ffmpeg",
            ],
            verify="ffmpeg -version or $FFMPEG_PATH -version should return successfully.",
        ),
    )


def probe_ollama_cli(
    *,
    env: dict[str, str] | os._Environ[str] = os.environ,
    runner: RunCommand = run_command,
    which: WhichCommand = shutil.which,
) -> Probe:
    return _version_probe(
        "ollama",
        ["--version"],
        env=env,
        runner=runner,
        which=which,
        remediation=_action(
            "Install or expose Ollama before local model runtime checks.",
            windows=["winget install Ollama.Ollama", "where ollama"],
            macos=["brew install ollama", "which ollama"],
            verify="ollama --version should return successfully.",
        ),
    )


def probe_openclaw(root: Path = ROOT, *, system_name: str | None = None) -> Probe:
    try:
        from core.openclaw_bridge import detect_openclaw_status
    except Exception as exc:  # noqa: BLE001
        return Probe(
            "openclaw_local_execution",
            False,
            "bridge_import_failed",
            {"error": str(exc)},
            _action(
                "Fix OpenClaw bridge import before runtime validation.",
                windows=["python -m py_compile core\\openclaw_bridge.py"],
                macos=["python -m py_compile core/openclaw_bridge.py"],
                verify="OpenClaw bridge should import successfully.",
            ),
        )
    status = detect_openclaw_status(root, system_name=system_name)
    local_execution = status.get("local_execution") or {}
    ok = bool(status.get("installed")) and bool(local_execution.get("supported"))
    return Probe(
        "openclaw_local_execution",
        ok,
        "ready" if ok else str(status.get("health") or "degraded"),
        status,
        _action(
            "Expose OpenClaw CLI and verify the local gateway health endpoint.",
            windows=[
                "openclaw --version",
                "python tools\\runtime_service_controller.py start --components openclaw --dry-run",
                "python tools\\runtime_service_controller.py start --components openclaw --allow-openclaw-mutation",
                "Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18789/healthz",
            ],
            macos=[
                "openclaw --version",
                "python tools/runtime_service_controller.py start --components openclaw --dry-run",
                "python tools/runtime_service_controller.py start --components openclaw --allow-openclaw-mutation",
                "curl http://127.0.0.1:18789/healthz",
            ],
            verify="openclaw_local_execution should report ready.",
        ),
    )


def collect_runtime_probes(
    root: Path = ROOT,
    *,
    env: dict[str, str] | os._Environ[str] = os.environ,
    system_name: str | None = None,
    runner: RunCommand = run_command,
    which: WhichCommand = shutil.which,
) -> list[Probe]:
    system_name = system_name or platform.system()
    return [
        probe_shell_context(root, env=env, system_name=system_name),
        probe_project_python(root, system_name=system_name, runner=runner),
        probe_node(env=env, runner=runner, which=which),
        probe_n8n_cli(env=env, runner=runner, which=which),
        probe_ffmpeg(env=env, runner=runner, which=which),
        probe_ollama_cli(env=env, runner=runner, which=which),
        probe_openclaw(root, system_name=system_name),
    ]


def build_payload(probes: list[Probe], root: Path = ROOT) -> dict[str, Any]:
    failed = [probe for probe in probes if not probe.ok]
    return {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(root),
        "ok": not failed,
        "status": "ready" if not failed else "attention_required",
        "failed_count": len(failed),
        "probes": [asdict(probe) for probe in probes],
        "next_actions": [
            {
                "source": probe.name,
                "status": probe.status,
                **probe.remediation,
                "evidence": probe.detail,
            }
            for probe in failed
        ],
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose local runtime dependencies across Windows/macOS shells.")
    parser.add_argument("--json-out", default=str(DEFAULT_REPORT))
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return 0 even when dependencies are missing; useful for inventory-only health checks.",
    )
    args = parser.parse_args()

    payload = build_payload(collect_runtime_probes(ROOT), ROOT)
    write_report(payload, Path(args.json_out))

    print("== Runtime Dependency Doctor ==")
    print(f"status: {payload['status']}")
    for probe in payload["probes"]:
        label = "OK" if probe["ok"] else "FAIL"
        print(f"[{label}] {probe['name']}: {probe['status']}")
    if payload["next_actions"]:
        print("next_actions:")
        for action in payload["next_actions"][:8]:
            print(f"- {action['source']}: {action['summary']}")
    return 0 if payload["ok"] or args.allow_missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

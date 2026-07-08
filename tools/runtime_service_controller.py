#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "runtime_service_controller_latest.json"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    ports: tuple[int, ...]
    command: tuple[str, ...]
    env: dict[str, str]
    log_file: str
    governed: bool = False


@dataclass
class ServiceResult:
    name: str
    ports: dict[str, bool]
    ok: bool
    status: str
    action: str
    command: list[str]
    log_file: str
    pid: int | None
    error: str
    governed: bool


PortChecker = Callable[[int], bool]
Launcher = Callable[[ServiceSpec, Path], tuple[int | None, str]]


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _platform_name(system_name: str | None = None) -> str:
    return system_name or platform.system()


def service_specs(root: Path = ROOT, system_name: str | None = None) -> dict[str, ServiceSpec]:
    system_name = _platform_name(system_name)
    logs = root / "logs"
    common_env = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }

    if system_name == "Windows":
        return {
            "web": ServiceSpec(
                "web",
                (5001,),
                (
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "tools" / "start_main_web_windows.ps1"),
                ),
                common_env,
                str(logs / "runtime_controller_web.log"),
            ),
            "n8n": ServiceSpec(
                "n8n",
                (5678, 5679),
                (
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "tools" / "n8n_watchdog_windows.ps1"),
                    "-Once",
                ),
                {
                    "N8N_HOST": "127.0.0.1",
                    "N8N_PORT": "5678",
                    "N8N_DIAGNOSTICS_ENABLED": "false",
                    "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
                    "N8N_TEMPLATES_ENABLED": "false",
                    "N8N_PERSONALIZATION_ENABLED": "false",
                    "N8N_PUBLIC_API_DISABLED": "true",
                    "N8N_HIRING_BANNER_ENABLED": "false",
                    "SKIP_STATISTICS_EVENTS": "true",
                    "EXTERNAL_FRONTEND_HOOKS_URLS": "",
                },
                str(logs / "runtime_controller_n8n.log"),
            ),
            "ollama": ServiceSpec(
                "ollama",
                (11434,),
                ("ollama", "serve"),
                {},
                str(logs / "runtime_controller_ollama.log"),
            ),
            "openclaw": ServiceSpec(
                "openclaw",
                (18789,),
                (str(Path(os.environ.get("USERPROFILE", "")) / ".openclaw" / "gateway.cmd"),),
                {},
                str(logs / "runtime_controller_openclaw.log"),
                governed=True,
            ),
        }

    return {
        "web": ServiceSpec(
            "web",
            (5001,),
            ("bash", str(root / "tools" / "start_web_server_5001.sh")),
            common_env,
            str(logs / "runtime_controller_web.log"),
        ),
        "n8n": ServiceSpec(
            "n8n",
            (5678, 5679),
            ("n8n", "start"),
            {
                "N8N_HOST": "127.0.0.1",
                "N8N_PORT": "5678",
                "N8N_DIAGNOSTICS_ENABLED": "false",
                "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
                "N8N_TEMPLATES_ENABLED": "false",
                "N8N_PERSONALIZATION_ENABLED": "false",
                "N8N_PUBLIC_API_DISABLED": "true",
                "N8N_HIRING_BANNER_ENABLED": "false",
                "SKIP_STATISTICS_EVENTS": "true",
                "EXTERNAL_FRONTEND_HOOKS_URLS": "",
            },
            str(logs / "runtime_controller_n8n.log"),
        ),
        "ollama": ServiceSpec(
            "ollama",
            (11434,),
            ("ollama", "serve"),
            {},
            str(logs / "runtime_controller_ollama.log"),
        ),
        "openclaw": ServiceSpec(
            "openclaw",
            (18789,),
            ("openclaw", "gateway", "--port", "18789"),
            {},
            str(logs / "runtime_controller_openclaw.log"),
            governed=True,
        ),
    }


def default_launcher(spec: ServiceSpec, root: Path = ROOT) -> tuple[int | None, str]:
    Path(spec.log_file).parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(spec.env)
    log = open(spec.log_file, "a", encoding="utf-8", errors="replace")
    creationflags = 0
    if platform.system() == "Windows" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(
            list(spec.command),
            cwd=str(root),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        log.close()
        return proc.pid, ""
    except Exception as exc:  # noqa: BLE001
        log.close()
        return None, str(exc)


def _ports_state(spec: ServiceSpec, port_checker: PortChecker = port_open) -> dict[str, bool]:
    return {str(port): port_checker(port) for port in spec.ports}


def _all_required_ports_listening(ports: dict[str, bool]) -> bool:
    return bool(ports) and all(ports.values())


def control_service(
    spec: ServiceSpec,
    *,
    action: str,
    root: Path = ROOT,
    dry_run: bool = False,
    allow_governed: bool = False,
    wait_seconds: int = 20,
    port_checker: PortChecker = port_open,
    launcher: Launcher = default_launcher,
    sleep: Callable[[float], None] = time.sleep,
) -> ServiceResult:
    before = _ports_state(spec, port_checker)
    if _all_required_ports_listening(before):
        return ServiceResult(
            spec.name,
            before,
            True,
            "ready",
            "already_listening",
            list(spec.command),
            spec.log_file,
            None,
            "",
            spec.governed,
        )

    if action == "status":
        return ServiceResult(
            spec.name,
            before,
            False,
            "not_listening",
            "status_only",
            list(spec.command),
            spec.log_file,
            None,
            "",
            spec.governed,
        )

    if spec.governed and not allow_governed:
        return ServiceResult(
            spec.name,
            before,
            False,
            "governance_required",
            "governed_skip",
            list(spec.command),
            spec.log_file,
            None,
            "OpenClaw start requires --allow-openclaw-mutation.",
            spec.governed,
        )

    if dry_run:
        return ServiceResult(
            spec.name,
            before,
            False,
            "would_start",
            "dry_run",
            list(spec.command),
            spec.log_file,
            None,
            "",
            spec.governed,
        )

    pid, error = launcher(spec, root)
    if error:
        return ServiceResult(
            spec.name,
            before,
            False,
            "start_failed",
            "start",
            list(spec.command),
            spec.log_file,
            pid,
            error,
            spec.governed,
        )

    deadline = time.monotonic() + max(0, wait_seconds)
    after = _ports_state(spec, port_checker)
    while not _all_required_ports_listening(after) and time.monotonic() < deadline:
        sleep(1)
        after = _ports_state(spec, port_checker)

    ok = _all_required_ports_listening(after)
    return ServiceResult(
        spec.name,
        after,
        ok,
        "ready" if ok else "started_waiting",
        "start",
        list(spec.command),
        spec.log_file,
        pid,
        "",
        spec.governed,
    )


def parse_components(raw: str, specs: dict[str, ServiceSpec]) -> list[str]:
    if raw.strip().lower() == "all":
        return list(specs)
    names = [item.strip().lower() for item in raw.split(",") if item.strip()]
    unknown = [name for name in names if name not in specs]
    if unknown:
        raise ValueError(f"unknown component(s): {', '.join(unknown)}")
    return names


def build_payload(results: list[ServiceResult], root: Path = ROOT) -> dict[str, Any]:
    ok = all(item.ok for item in results)
    def controller_command(item: ServiceResult) -> list[str]:
        command = [
            "python",
            "tools/runtime_service_controller.py",
            "start",
            "--components",
            item.name,
        ]
        if item.governed:
            command.append("--allow-openclaw-mutation")
        return command

    return {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(root),
        "ok": ok,
        "status": "ready" if ok else "attention_required",
        "results": [asdict(item) for item in results],
        "next_actions": [
            {
                "source": item.name,
                "status": item.status,
                "summary": (
                    "Approve and start OpenClaw Gateway."
                    if item.governed
                    else "Start or inspect runtime service."
                ),
                "governed": item.governed,
                "controller_command": controller_command(item),
                "command": item.command,
                "log_file": item.log_file,
                "evidence": {"ports": item.ports, "error": item.error},
            }
            for item in results
            if not item.ok
        ],
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Status and controlled startup for local runtime services.")
    parser.add_argument("action", choices=("status", "start"), nargs="?", default="status")
    parser.add_argument("--components", default="all", help="Comma list: web,n8n,ollama,openclaw or all.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-openclaw-mutation", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=20)
    parser.add_argument("--json-out", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    specs = service_specs(ROOT)
    try:
        components = parse_components(args.components, specs)
    except ValueError as exc:
        parser.error(str(exc))

    results = [
        control_service(
            specs[name],
            action=args.action,
            root=ROOT,
            dry_run=args.dry_run,
            allow_governed=args.allow_openclaw_mutation,
            wait_seconds=args.wait_seconds,
        )
        for name in components
    ]
    payload = build_payload(results, ROOT)
    write_report(payload, Path(args.json_out))

    print("== Runtime Service Controller ==")
    print(f"action: {args.action} dry_run={args.dry_run}")
    for item in results:
        label = "OK" if item.ok else "WAIT"
        print(f"[{label}] {item.name}: {item.status} action={item.action} ports={item.ports}")
        if item.error:
            print(f"  error: {item.error}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

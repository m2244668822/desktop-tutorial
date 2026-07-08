"""OpenClaw integration helpers for runtime status and governance checks."""

from __future__ import annotations

import subprocess
import socket
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENCLAW_GATEWAY_HOST = "127.0.0.1"
OPENCLAW_GATEWAY_PORT = 18789


def _run_command(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:
        return 1, "", str(exc)


def _tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_get_json(url: str, timeout: int = 4) -> dict[str, Any]:
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload: Any = json.loads(raw) if raw else None
            except Exception:
                payload = raw[:300]
            return {"ok": True, "status_code": resp.status, "data": payload, "error": ""}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status_code": exc.code, "data": body[:300], "error": str(exc)}
    except URLError as exc:
        return {"ok": False, "status_code": 0, "data": None, "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status_code": 0, "data": None, "error": str(exc)}


def _schtasks_state(output: str) -> str:
    flat = output.replace("\r", "")
    for line in flat.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == "status":
            lowered = value.strip().lower()
            if "running" in lowered:
                return "running"
            if "ready" in lowered or "stopped" in lowered:
                return "stopped"
            return lowered or "unknown"
    if "Status:" in flat and "Running" in flat:
        return "running"
    return "unknown"


def build_openclaw_governance(status: dict[str, Any]) -> dict[str, Any]:
    system_name = str(status.get("platform") or platform.system())
    installed = bool(status.get("installed"))
    daemon_installed = bool(status.get("daemon_installed"))
    daemon_running = bool(status.get("daemon_running"))
    local_supported = bool((status.get("local_execution") or {}).get("supported"))
    decision_state = "cli_unavailable"
    next_action = "Install or expose the OpenClaw CLI before daemon work."
    health = "unavailable"

    if installed and daemon_running and local_supported:
        decision_state = "running"
        next_action = "Keep observing through /api/get_status; mutations still require prophet approval."
        health = "ready"
    elif installed and daemon_running:
        decision_state = "gateway_unhealthy"
        next_action = "Inspect the OpenClaw Gateway health endpoint before using local execution."
        health = "degraded"
    elif installed and daemon_installed:
        decision_state = "prophet_decision_required"
        next_action = "Ask the prophet role to approve starting or changing OpenClaw Gateway."
        health = "governed_stopped"
    elif installed and system_name != "Windows":
        decision_state = "prophet_decision_required"
        next_action = "Ask the prophet role to approve starting OpenClaw Gateway on this host."
        health = "governed_stopped"
    elif installed:
        decision_state = "task_missing"
        next_action = "Review whether OpenClaw Gateway should be installed as a managed task."
        health = "degraded"

    return {
        "health": health,
        "decision_state": decision_state,
        "auto_start_allowed": False,
        "prophet_required_for_mutation": True,
        "recommended_next_action": next_action,
        "handoff_phrase": "我確認，請申言者決策後再交工程師執行 OpenClaw 整合。",
    }


def detect_gateway_health(
    host: str = OPENCLAW_GATEWAY_HOST,
    port: int = OPENCLAW_GATEWAY_PORT,
) -> dict[str, Any]:
    health_url = f"http://{host}:{port}/healthz"
    listening = _tcp_open(host, port)
    response = _http_get_json(health_url) if listening else {
        "ok": False,
        "status_code": 0,
        "data": None,
        "error": "port_not_listening",
    }
    payload = response.get("data")
    status_text = ""
    if isinstance(payload, dict):
        status_text = str(payload.get("status") or "")
    payload_ok = not isinstance(payload, dict) or (
        bool(payload.get("ok", True))
        and status_text.lower() in {"", "live", "ok", "ready"}
    )
    ok = bool(response.get("ok")) and payload_ok
    return {
        "host": host,
        "port": port,
        "url": health_url,
        "listening": listening,
        "health_ok": ok,
        "response": response,
    }


def _openclaw_version_command(system_name: str) -> list[str]:
    if system_name == "Windows":
        return ["cmd", "/c", "openclaw --version"]
    return ["openclaw", "--version"]


def detect_openclaw_status(
    workspace: Path | None = None,
    system_name: str | None = None,
) -> dict[str, Any]:
    """Return compact OpenClaw runtime and daemon status for system snapshots."""
    now = datetime.now().isoformat(timespec="seconds")
    ws = str(workspace) if workspace else ""
    system_name = system_name or platform.system()
    status: dict[str, Any] = {
        "checked_at": now,
        "platform": system_name,
        "workspace": ws,
        "installed": False,
        "version": "",
        "daemon_task_name": "OpenClaw Gateway",
        "daemon_installed": False,
        "daemon_running": False,
        "daemon_state": "unknown",
        "gateway": detect_gateway_health(),
        "local_execution": {
            "supported": False,
            "criteria": {
                "cli_installed": False,
                "gateway_listening": False,
                "gateway_health_ok": False,
            },
        },
        "health": "unavailable",
        "governance": {},
        "notes": [],
    }

    rc, out, err = _run_command(_openclaw_version_command(system_name))
    if rc == 0 and out:
        status["installed"] = True
        status["version"] = out.splitlines()[0].strip()
        status["local_execution"]["criteria"]["cli_installed"] = True
    else:
        status["notes"].append(f"openclaw_cli_unavailable: {(err or out)[:160]}")
        status["governance"] = build_openclaw_governance(status)
        return status

    gateway = status["gateway"]
    status["local_execution"]["criteria"]["gateway_listening"] = bool(
        gateway.get("listening")
    )
    status["local_execution"]["criteria"]["gateway_health_ok"] = bool(
        gateway.get("health_ok")
    )
    status["local_execution"]["supported"] = all(
        bool(value) for value in status["local_execution"]["criteria"].values()
    )

    if system_name != "Windows":
        gateway_ok = bool(gateway.get("health_ok"))
        status["daemon_state"] = "running" if gateway_ok else "not_applicable"
        status["daemon_running"] = gateway_ok
        status["notes"].append("windows_scheduled_task_not_applicable")
        if not gateway_ok:
            status["notes"].append("gateway_not_running")
        status["governance"] = build_openclaw_governance(status)
        status["health"] = status["governance"]["health"]
        return status

    rc, out, err = _run_command(
        ["schtasks", "/Query", "/TN", "OpenClaw Gateway", "/FO", "LIST", "/V"]
    )
    if rc != 0:
        status["notes"].append(f"task_query_failed: {(err or out)[:160]}")
        status["governance"] = build_openclaw_governance(status)
        status["health"] = status["governance"]["health"]
        return status

    status["daemon_installed"] = True
    daemon_state = _schtasks_state(out)
    gateway_ok = bool(gateway.get("health_ok"))
    is_running = daemon_state == "running" or gateway_ok
    status["daemon_running"] = is_running
    status["daemon_state"] = "running" if is_running else "stopped"
    if daemon_state != "running" and gateway_ok:
        status["notes"].append("task_not_running_but_gateway_live")
    if not is_running:
        status["notes"].append("daemon_not_running")
    status["governance"] = build_openclaw_governance(status)
    status["health"] = status["governance"]["health"]
    return status

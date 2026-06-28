"""OpenClaw integration helpers for runtime status and governance checks."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


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
    installed = bool(status.get("installed"))
    daemon_installed = bool(status.get("daemon_installed"))
    daemon_running = bool(status.get("daemon_running"))
    decision_state = "cli_unavailable"
    next_action = "Install or expose the OpenClaw CLI before daemon work."
    health = "unavailable"

    if installed and daemon_running:
        decision_state = "running"
        next_action = "Keep observing through /api/get_status; mutations still require prophet approval."
        health = "ready"
    elif installed and daemon_installed:
        decision_state = "prophet_decision_required"
        next_action = "Ask the prophet role to approve starting or changing OpenClaw Gateway."
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


def detect_openclaw_status(workspace: Path | None = None) -> dict[str, Any]:
    """Return compact OpenClaw runtime and daemon status for system snapshots."""
    now = datetime.now().isoformat(timespec="seconds")
    ws = str(workspace) if workspace else ""
    status: dict[str, Any] = {
        "checked_at": now,
        "workspace": ws,
        "installed": False,
        "version": "",
        "daemon_task_name": "OpenClaw Gateway",
        "daemon_installed": False,
        "daemon_running": False,
        "daemon_state": "unknown",
        "health": "unavailable",
        "governance": {},
        "notes": [],
    }

    rc, out, err = _run_command(["cmd", "/c", "openclaw --version"])
    if rc == 0 and out:
        status["installed"] = True
        status["version"] = out.splitlines()[0].strip()
    else:
        status["notes"].append(f"openclaw_cli_unavailable: {(err or out)[:160]}")
        status["governance"] = build_openclaw_governance(status)
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
    is_running = daemon_state == "running"
    status["daemon_running"] = is_running
    status["daemon_state"] = "running" if is_running else "stopped"
    if not is_running:
        status["notes"].append("daemon_not_running")
    status["governance"] = build_openclaw_governance(status)
    status["health"] = status["governance"]["health"]
    return status

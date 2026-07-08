#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
N8N_DB = Path.home() / ".n8n" / "database.sqlite"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class Check:
    name: str
    ok: bool
    status: str
    detail: dict[str, Any]


def _action(
    source: str,
    priority: str,
    summary: str,
    *,
    windows: list[str] | None = None,
    macos: list[str] | None = None,
    verify: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "priority": priority,
        "summary": summary,
        "windows": windows or [],
        "macos": macos or [],
        "verify": verify,
        "evidence": evidence or {},
    }


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for action in actions:
        key = (str(action.get("source")), str(action.get("summary")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def tcp_open(port: int, host: str = "127.0.0.1", timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(path: str, port: int = 5001, timeout: int = 5) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}{path}"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload: Any = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = raw[:500]
            return {"ok": True, "status_code": resp.status, "data": payload, "error": ""}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status_code": exc.code, "data": body[:500], "error": str(exc)}
    except URLError as exc:
        return {"ok": False, "status_code": 0, "data": None, "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status_code": 0, "data": None, "error": str(exc)}


def _path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
    except OSError:
        return False


def check_workspace_context() -> Check:
    cwd = Path.cwd()
    root = ROOT.resolve()
    expected_files = [
        "desktop_chat_app.py",
        "templates/chat.html",
        "tools/foundation_health_check.py",
        "docs/dev/FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md",
    ]
    required = {rel: (root / rel).exists() for rel in expected_files}
    git_proc = run(["git", "rev-parse", "--show-toplevel"], timeout=10)
    git_root_raw = git_proc.stdout.strip() if git_proc.returncode == 0 else ""
    git_root = ""
    git_root_matches = False
    if git_root_raw:
        try:
            git_root = str(Path(git_root_raw).resolve())
            git_root_matches = git_root.casefold() == str(root).casefold()
        except OSError:
            git_root = git_root_raw
    cwd_inside_root = _path_inside(cwd, root)

    env_paths: dict[str, dict[str, Any]] = {}
    for name in ("PWD", "OLDPWD", "CODEX_WORKSPACE", "WORKSPACE", "GITHUB_WORKSPACE"):
        value = os.environ.get(name)
        if not value:
            continue
        try:
            env_path = Path(value).expanduser()
            env_paths[name] = {"value": value, "exists": env_path.exists()}
        except Exception as exc:  # noqa: BLE001
            env_paths[name] = {"value": value, "exists": False, "error": str(exc)}

    ok = all(required.values()) and git_proc.returncode == 0 and git_root_matches
    if not ok:
        status = "git_root_mismatch" if git_proc.returncode == 0 and not git_root_matches else "invalid_workspace"
    elif not cwd_inside_root:
        status = "ready_external_cwd"
    else:
        status = "ready"
    return Check(
        "workspace_context",
        ok,
        status,
        {
            "root": str(root),
            "cwd": str(cwd),
            "cwd_inside_root": cwd_inside_root,
            "git_root": git_root,
            "git_returncode": git_proc.returncode,
            "git_stderr": git_proc.stderr[-1000:],
            "required_files": required,
            "env_paths": env_paths,
        },
    )


def check_ports() -> Check:
    expected = {
        5001: "main_web_gateway",
        5678: "n8n_editor",
        5679: "n8n_task_broker",
        11434: "ollama",
    }
    ports = {
        str(port): {"role": role, "listening": tcp_open(port)}
        for port, role in expected.items()
    }
    ok = all(item["listening"] for item in ports.values())
    return Check("ports", ok, "ready" if ok else "degraded", ports)


def check_gateway() -> Check:
    status = http_get("/status")
    policy = http_get("/api/gateway/policy")
    runtime = http_get("/api/get_status")
    ok = status["ok"] and policy["ok"] and runtime["ok"]
    openclaw = {}
    if isinstance(runtime.get("data"), dict):
        openclaw = (
            runtime["data"].get("monitor", {}).get("openclaw")
            or runtime["data"].get("monitoring", {}).get("openclaw")
            or {}
        )
    status_label = "ready" if ok else "degraded"
    if ok and openclaw.get("installed") and not openclaw.get("daemon_running"):
        status_label = "ready_with_openclaw_stopped"
    return Check(
        "gateway",
        ok,
        status_label,
        {
            "status": status,
            "policy": policy,
            "get_status": {"ok": runtime["ok"], "status_code": runtime["status_code"]},
            "openclaw": openclaw,
        },
    )


def check_openclaw_runtime() -> Check:
    try:
        from core.openclaw_bridge import detect_openclaw_status
    except Exception as exc:  # noqa: BLE001
        return Check(
            "openclaw_runtime",
            False,
            "bridge_import_failed",
            {"error": str(exc)},
        )
    try:
        status = detect_openclaw_status(ROOT)
    except Exception as exc:  # noqa: BLE001
        return Check(
            "openclaw_runtime",
            False,
            "detect_failed",
            {"error": str(exc)},
        )
    local_execution = status.get("local_execution") or {}
    supported = bool(local_execution.get("supported"))
    installed = bool(status.get("installed"))
    ok = installed
    check_status = "ready" if supported else str(status.get("health") or "degraded")
    return Check("openclaw_runtime", ok, check_status, status)


def check_runtime_dependencies() -> Check:
    try:
        from tools.runtime_dependency_doctor import build_payload, collect_runtime_probes
    except Exception as exc:  # noqa: BLE001
        return Check(
            "runtime_dependencies",
            False,
            "doctor_import_failed",
            {"error": str(exc)},
        )
    try:
        payload = build_payload(collect_runtime_probes(ROOT), ROOT)
    except Exception as exc:  # noqa: BLE001
        return Check(
            "runtime_dependencies",
            False,
            "doctor_failed",
            {"error": str(exc)},
        )
    return Check(
        "runtime_dependencies",
        bool(payload.get("ok")),
        str(payload.get("status") or "unknown"),
        payload,
    )


def check_runtime_service_controller() -> Check:
    report_path = ROOT / "reports" / "runtime_service_controller_health_latest.json"
    cmd = [
        sys.executable,
        "tools/runtime_service_controller.py",
        "status",
        "--json-out",
        str(report_path),
    ]
    proc = run(cmd, timeout=90)
    detail: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
        "report_path": str(report_path),
    }
    payload: dict[str, Any] = {}
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            detail["report"] = payload
        except Exception as exc:  # noqa: BLE001
            detail["report_error"] = str(exc)
    status = str(payload.get("status") or ("ready" if proc.returncode == 0 else "failed"))
    ok = proc.returncode == 0 and bool(payload.get("ok"))
    return Check("runtime_service_controller", ok, status, detail)


def check_n8n() -> Check:
    health = http_get("/healthz", port=5678)
    readiness = http_get("/healthz/readiness", port=5678)
    broker = http_get("/healthz", port=5679)
    counts: dict[str, int] = {}
    db_ok = False
    db_error = ""
    if N8N_DB.exists():
        try:
            con = sqlite3.connect(f"file:{N8N_DB}?mode=ro", uri=True)
            for table in (
                "workflow_entity",
                "credentials_entity",
                "execution_entity",
                "webhook_entity",
            ):
                counts[table] = int(con.execute(f"select count(*) from {table}").fetchone()[0])
            con.close()
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_error = str(exc)
    else:
        db_error = f"missing db: {N8N_DB}"
    ok = health["ok"] and readiness["ok"] and broker["ok"] and db_ok
    status = "ready" if ok and counts.get("workflow_entity", 0) > 0 else "degraded"
    return Check(
        "n8n",
        ok,
        status,
        {
            "health": health,
            "readiness": readiness,
            "broker": broker,
            "db_path": str(N8N_DB),
            "db_ok": db_ok,
            "db_error": db_error,
            "counts": counts,
        },
    )


def check_n8n_workflow_preflight() -> Check:
    report_path = ROOT / "reports" / "n8n_workflow_preflight_latest.json"
    cmd = [
        sys.executable,
        "tools/n8n_workflow_preflight.py",
        "--allow-blockers",
        "--json-out",
        str(report_path),
    ]
    proc = run(cmd, timeout=60)
    detail: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
        "report_path": str(report_path),
    }
    payload: dict[str, Any] = {}
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            detail["report"] = payload
        except Exception as exc:  # noqa: BLE001
            detail["report_error"] = str(exc)
    status = str(payload.get("status") or ("ready" if proc.returncode == 0 else "failed"))
    ok = proc.returncode == 0 and status in {
        "ready_for_activation",
        "blocked_for_activation",
    }
    return Check("n8n_workflow_preflight", ok, status, detail)


def check_knowledge_hub() -> Check:
    manifest_path = ROOT / "data" / "knowledge_hub" / "manifest.json"
    if not manifest_path.exists():
        return Check("knowledge_hub", False, "missing_manifest", {"path": str(manifest_path)})
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return Check(
            "knowledge_hub",
            False,
            "invalid_manifest",
            {"path": str(manifest_path), "error": str(exc)},
        )
    ready = all(
        bool(manifest.get(key))
        for key in ("chatgpt_database_ready", "sqlite_ready", "faiss_ready")
    )
    total_items = int(manifest.get("total_items", 0) or 0)
    ok = ready and total_items > 0
    return Check(
        "knowledge_hub",
        ok,
        "ready" if ok else "degraded",
        {
            "path": str(manifest_path),
            "generated_at": manifest.get("generated_at", ""),
            "workspace": manifest.get("workspace", ""),
            "total_items": total_items,
            "by_source": manifest.get("by_source", {}),
        },
    )


def check_frontend_static_contract() -> Check:
    template = ROOT / "templates" / "chat.html"
    if not template.exists():
        return Check("frontend_static_contract", False, "missing_template", {"path": str(template)})
    html = template.read_text(encoding="utf-8", errors="replace")
    required_tokens = [
        "/chat/agent",
        "/api/orchestrator/status",
        "/trace/learning-status",
        "function bootstrapPolling()",
        "function syncModelHeader()",
        'let _tasksFilter = "unresolved";',
        "const PROVIDER_RATE_LIMIT_BACKOFF_MS = 1800000;",
        "function renderAgentActivityBoard()",
        'id="agentActivityBoard"',
        'id="mon-openclaw"',
        "function updateOpenClawMonitor(openclaw = {})",
        'fetch("/api/get_status", { headers: ah })',
        "@media (max-width: 640px)",
        ".right-panel{display:none}",
        ".model-grid{grid-template-columns:1fr;gap:7px}",
        ".tasks-header{align-items:flex-start;gap:6px;flex-direction:column}",
        "未載入",
        "尚未載入 OpenClaw 狀態",
        "運行中",
        "已停止",
        "需申言者",
        "待申言者決策",
        'label: "未解"',
        'label: "待執行"',
        'label: "執行中"',
        'label: "已完成"',
        'label: "失敗"',
    ]
    forbidden_tokens = [
        "http://127.0.0.1:7861/ingest/",
        "/static/branding/topbar-logo.png",
    ]
    mojibake_markers = [
        "\ufffd",
        "Ã",
        "Â",
        "â€™",
        "蝡",
        "嚗",
        "摰",
        "撠",
        "撌",
        "瘚",
        "銝",
        "頛",
        "撽",
        "霅",
        "甇",
    ]
    private_use = sorted({ch for ch in html if 0xE000 <= ord(ch) <= 0xF8FF})
    missing = [token for token in required_tokens if token not in html]
    forbidden = [token for token in forbidden_tokens if token in html]
    mojibake = [token for token in mojibake_markers if token in html]
    ok = not missing and not forbidden and not mojibake and not private_use
    return Check(
        "frontend_static_contract",
        ok,
        "ready" if ok else "contract_drift",
        {
            "path": str(template),
            "missing": missing,
            "forbidden": forbidden,
            "mojibake": mojibake,
            "private_use_codepoints": [f"U+{ord(ch):04X}" for ch in private_use[:20]],
        },
    )


def check_git() -> Check:
    proc = run(["git", "status", "--short", "--branch"], timeout=10)
    fsck = run(["git", "fsck", "--full", "--no-reflogs"], timeout=120)
    status_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    dirty_lines = [line for line in status_lines if not line.startswith("##")]
    fsck_text = (fsck.stdout + "\n" + fsck.stderr).strip()
    fatal_markers = ("fatal:", "error:", "missing blob", "bad object", "invalid sha1")
    fatal = any(marker in fsck_text.lower() for marker in fatal_markers)
    ok = proc.returncode == 0 and fsck.returncode == 0 and not fatal
    return Check(
        "git",
        ok,
        "dirty" if ok and dirty_lines else ("ready" if ok else "corrupt_or_error"),
        {
            "status": status_lines,
            "dirty_count": len(dirty_lines),
            "fsck_returncode": fsck.returncode,
            "fsck_note": fsck_text[:1000],
        },
    )


def check_py_compile() -> Check:
    files = [
        "desktop_chat_app.py",
        "core/web_server.py",
        "core/openclaw_bridge.py",
        "core/knowledge_hub.py",
        "core/workflow_runtime.py",
        "core/langgraph_workflow.py",
        "tools/foundation_health_check.py",
        "tools/runtime_binary_locator.py",
        "tools/runtime_dependency_doctor.py",
        "tools/runtime_service_controller.py",
        "tools/chat_shell_browser_smoke.py",
        "tools/n8n_workflow_preflight.py",
        "tools/foundation_goal_audit.py",
    ]
    cmd = [sys.executable, "-m", "py_compile", *files]
    proc = run(cmd, timeout=120)
    ok = proc.returncode == 0
    return Check(
        "py_compile",
        ok,
        "ready" if ok else "compile_failed",
        {"files": files, "stdout": proc.stdout[-1000:], "stderr": proc.stderr[-2000:]},
    )


def check_browser_smoke(mode: str = "auto") -> Check:
    report_path = ROOT / "reports" / "chat_shell_browser_smoke_latest.json"
    screenshot_path = ROOT / "reports" / "chat_shell_browser_smoke_latest.png"
    cmd = [
        sys.executable,
        "tools/chat_shell_browser_smoke.py",
        "--base-url",
        "http://127.0.0.1:5001",
        "--json-out",
        str(report_path),
        "--screenshot-out",
        str(screenshot_path),
        "--timeout",
        "20",
    ]
    proc = run(cmd, timeout=60)
    detail: dict[str, Any] = {
        "mode": mode,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
        "report_path": str(report_path),
        "screenshot_path": str(screenshot_path),
    }
    payload: dict[str, Any] = {}
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            detail["report"] = payload
        except Exception as exc:  # noqa: BLE001
            detail["report_error"] = str(exc)

    status = str(payload.get("status") or ("ready" if proc.returncode == 0 else "failed"))
    if status == "browser_not_found" and mode == "auto":
        return Check("browser_smoke", True, "skipped_browser_not_found", detail)
    ok = proc.returncode == 0 and bool(payload.get("ok", proc.returncode == 0))
    return Check("browser_smoke", ok, "ready" if ok else status, detail)


def collect_checks(browser_smoke: str = "auto") -> list[Check]:
    checks = [
        check_workspace_context(),
        check_runtime_dependencies(),
        check_runtime_service_controller(),
        check_ports(),
        check_gateway(),
        check_openclaw_runtime(),
        check_n8n(),
        check_n8n_workflow_preflight(),
        check_knowledge_hub(),
        check_frontend_static_contract(),
        check_git(),
        check_py_compile(),
    ]
    if browser_smoke != "off":
        checks.append(check_browser_smoke(browser_smoke))
    return checks


def build_next_actions(checks: list[Check]) -> list[dict[str, Any]]:
    by_name = {check.name: check for check in checks}
    actions: list[dict[str, Any]] = []

    workspace = by_name.get("workspace_context")
    if workspace and not workspace.ok:
        actions.append(
            _action(
                "workspace_context",
                "P0",
                "Fix the shell workspace path before debugging app services.",
                windows=[
                    f"Set-Location '{ROOT}'",
                    "git rev-parse --show-toplevel",
                ],
                macos=[
                    "cd /Volumes/<volume>/<repo>",
                    "git rev-parse --show-toplevel",
                ],
                verify="workspace_context should report ready or ready_external_cwd.",
                evidence=workspace.detail,
            )
        )

    runtime_dependencies = by_name.get("runtime_dependencies")
    if runtime_dependencies and not runtime_dependencies.ok:
        for action in list(runtime_dependencies.detail.get("next_actions") or [])[:8]:
            actions.append(
                _action(
                    "runtime_dependencies",
                    "P1",
                    str(action.get("summary") or action.get("source") or "Fix runtime dependency."),
                    windows=list(action.get("windows") or []),
                    macos=list(action.get("macos") or []),
                    verify=str(action.get("verify") or "runtime_dependencies should report ready."),
                    evidence={
                        "source": action.get("source"),
                        "status": action.get("status"),
                        "evidence": action.get("evidence", {}),
                    },
                )
            )

    runtime_controller = by_name.get("runtime_service_controller")
    if runtime_controller and not runtime_controller.ok:
        report = runtime_controller.detail.get("report") or {}
        for action in list(report.get("next_actions") or [])[:8]:
            command = list(action.get("controller_command") or [])
            actions.append(
                _action(
                    "runtime_service_controller",
                    "P1",
                    str(action.get("summary") or action.get("source") or "Start or inspect runtime service."),
                    windows=[" ".join(command)] if command else [],
                    macos=[" ".join(command)] if command else [],
                    verify="runtime_service_controller should report ready.",
                    evidence={
                        "source": action.get("source"),
                        "status": action.get("status"),
                        "governed": action.get("governed"),
                        "evidence": action.get("evidence", {}),
                    },
                )
            )
        if not report.get("next_actions"):
            actions.append(
                _action(
                    "runtime_service_controller",
                    "P1",
                    "Fix runtime service controller status before trusting service readiness.",
                    windows=["python tools\\runtime_service_controller.py status"],
                    macos=["python tools/runtime_service_controller.py status"],
                    verify="runtime_service_controller should report ready.",
                    evidence=runtime_controller.detail,
                )
            )

    ports = by_name.get("ports")
    if ports and not ports.ok:
        missing = [
            f"{port}:{item.get('role')}"
            for port, item in ports.detail.items()
            if not item.get("listening")
        ]
        actions.append(
            _action(
                "ports",
                "P1",
                "Start or verify missing runtime services.",
                windows=[
                    "python tools\\runtime_service_controller.py start --components web,n8n,ollama --dry-run",
                    "python tools\\runtime_service_controller.py start --components web,n8n,ollama",
                    "powershell -ExecutionPolicy Bypass -File tools\\enforce_single_entry_gateway.ps1",
                ],
                macos=[
                    "python tools/runtime_service_controller.py start --components web,n8n,ollama --dry-run",
                    "python tools/runtime_service_controller.py start --components web,n8n,ollama",
                ],
                verify="Rerun python tools/foundation_health_check.py --browser-smoke off.",
                evidence={"missing": missing},
            )
        )

    gateway = by_name.get("gateway")
    if gateway and not gateway.ok:
        actions.append(
            _action(
                "gateway",
                "P1",
                "Bring the main web gateway up before running browser smoke.",
                windows=[
                    "python tools\\runtime_service_controller.py start --components web --dry-run",
                    "python tools\\runtime_service_controller.py start --components web",
                ],
                macos=[
                    "python tools/runtime_service_controller.py start --components web --dry-run",
                    "python tools/runtime_service_controller.py start --components web",
                ],
                verify="/status and /api/gateway/policy should return 200.",
                evidence={
                    "status": gateway.detail.get("status", {}),
                    "policy": gateway.detail.get("policy", {}),
                },
            )
        )

    n8n = by_name.get("n8n")
    if n8n and not n8n.ok:
        actions.append(
            _action(
                "n8n",
                "P1",
                "Start n8n and confirm its editor, broker, and SQLite database are inspectable.",
                windows=[
                    "python tools\\runtime_service_controller.py start --components n8n --dry-run",
                    "python tools\\runtime_service_controller.py start --components n8n",
                ],
                macos=[
                    "python tools/runtime_service_controller.py start --components n8n --dry-run",
                    "python tools/runtime_service_controller.py start --components n8n",
                ],
                verify="n8n health/readiness/broker should be OK and db_ok should be true.",
                evidence={
                    "db_path": n8n.detail.get("db_path"),
                    "db_ok": n8n.detail.get("db_ok"),
                    "counts": n8n.detail.get("counts", {}),
                },
            )
        )

    openclaw = by_name.get("openclaw_runtime")
    if openclaw:
        local_execution = openclaw.detail.get("local_execution") or {}
        criteria = local_execution.get("criteria") or {}
        if not openclaw.ok:
            actions.append(
                _action(
                    "openclaw_runtime",
                    "P1",
                    "Install or expose OpenClaw before claiming local execution support.",
                    windows=["openclaw --version"],
                    macos=["openclaw --version"],
                    verify="openclaw_runtime should report installed=true.",
                    evidence=openclaw.detail,
                )
            )
        elif not local_execution.get("supported"):
            actions.append(
                _action(
                    "openclaw_runtime",
                    "P1",
                    "Start and verify the local OpenClaw Gateway health endpoint.",
                    windows=[
                        "python tools\\runtime_service_controller.py start --components openclaw --dry-run",
                        "python tools\\runtime_service_controller.py start --components openclaw --allow-openclaw-mutation",
                        "Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18789/healthz",
                    ],
                    macos=[
                        "python tools/runtime_service_controller.py start --components openclaw --dry-run",
                        "python tools/runtime_service_controller.py start --components openclaw --allow-openclaw-mutation",
                        "curl http://127.0.0.1:18789/healthz",
                    ],
                    verify="openclaw_runtime local_execution.supported should be true.",
                    evidence={
                        "health": openclaw.detail.get("health"),
                        "criteria": criteria,
                        "gateway": openclaw.detail.get("gateway", {}),
                    },
                )
            )

    preflight = by_name.get("n8n_workflow_preflight")
    if preflight:
        report = (preflight.detail.get("report") or {}) if isinstance(preflight.detail, dict) else {}
        if preflight.status == "blocked_for_activation":
            remediation = report.get("remediation_plan") or []
            if remediation:
                for item in remediation[:8]:
                    actions.append(
                        _action(
                            "n8n_workflow_preflight",
                            "P1",
                            str(item.get("summary") or item.get("code") or "Resolve n8n blocker."),
                            windows=list(item.get("windows") or []),
                            macos=list(item.get("macos") or []),
                            verify=str(item.get("verify") or "Rerun tools/n8n_workflow_preflight.py."),
                            evidence={
                                "code": item.get("code"),
                                "severity": item.get("severity"),
                                "manual": item.get("manual"),
                                "issue_evidence": item.get("evidence", {}),
                            },
                        )
                    )
            else:
                actions.append(
                    _action(
                        "n8n_workflow_preflight",
                        "P1",
                        "Inspect n8n workflow blockers before activation.",
                        windows=["python tools\\n8n_workflow_preflight.py --allow-blockers"],
                        macos=["python tools/n8n_workflow_preflight.py --allow-blockers"],
                        verify="Preflight should report ready_for_activation before enabling workflow.",
                        evidence={"status": preflight.status},
                    )
                )
        elif not preflight.ok:
            actions.append(
                _action(
                    "n8n_workflow_preflight",
                    "P1",
                    "Fix n8n preflight execution before trusting workflow activation state.",
                    windows=["python tools\\n8n_workflow_preflight.py --allow-blockers"],
                    macos=["python tools/n8n_workflow_preflight.py --allow-blockers"],
                    verify="The preflight command should return a JSON report.",
                    evidence={"status": preflight.status},
                )
            )

    frontend = by_name.get("frontend_static_contract")
    if frontend and not frontend.ok:
        actions.append(
            _action(
                "frontend_static_contract",
                "P1",
                "Restore canonical chat shell contract tokens before browser validation.",
                windows=["python -m pytest tests\\test_frontend_sync_contract.py --tb=short"],
                macos=["python -m pytest tests/test_frontend_sync_contract.py --tb=short"],
                verify="frontend_static_contract should report ready.",
                evidence=frontend.detail,
            )
        )

    browser = by_name.get("browser_smoke")
    if browser and not browser.ok:
        actions.append(
            _action(
                "browser_smoke",
                "P1",
                "Fix real browser /chat_shell runtime, console, or layout failures.",
                windows=["python tools\\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001"],
                macos=["python tools/chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001"],
                verify="browser_smoke should report ready.",
                evidence={"status": browser.status, "report_path": browser.detail.get("report_path")},
            )
        )

    compile_check = by_name.get("py_compile")
    if compile_check and not compile_check.ok:
        actions.append(
            _action(
                "py_compile",
                "P0",
                "Fix Python syntax/import compile failures before runtime testing.",
                windows=[
                    "python -m py_compile desktop_chat_app.py core\\web_server.py core\\openclaw_bridge.py tools\\foundation_health_check.py tools\\runtime_dependency_doctor.py tools\\runtime_service_controller.py"
                ],
                macos=[
                    "python -m py_compile desktop_chat_app.py core/web_server.py core/openclaw_bridge.py tools/foundation_health_check.py tools/runtime_dependency_doctor.py tools/runtime_service_controller.py"
                ],
                verify="py_compile should report ready.",
                evidence=compile_check.detail,
            )
        )

    git_check = by_name.get("git")
    if git_check and git_check.ok and git_check.status == "dirty":
        actions.append(
            _action(
                "git",
                "P3",
                "Review dirty worktree files and keep generated reports out of source commits.",
                windows=["git status -sb", "git diff --stat"],
                macos=["git status -sb", "git diff --stat"],
                verify="Only intentional source changes should be staged.",
                evidence={"dirty_count": git_check.detail.get("dirty_count")},
            )
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    source_order = {
        "workspace_context": 0,
        "runtime_dependencies": 1,
        "runtime_service_controller": 2,
        "ports": 3,
        "gateway": 4,
        "openclaw_runtime": 5,
        "n8n": 6,
        "n8n_workflow_preflight": 7,
        "frontend_static_contract": 8,
        "browser_smoke": 9,
        "py_compile": 10,
        "git": 11,
    }
    return sorted(
        _dedupe_actions(actions),
        key=lambda item: (
            priority_order.get(str(item.get("priority")), 99),
            source_order.get(str(item.get("source")), 99),
            str(item.get("source")),
        ),
    )


def summarize_next_actions(actions: list[dict[str, Any]]) -> dict[str, Any]:
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    by_priority: dict[str, int] = {}
    for action in actions:
        priority = str(action.get("priority") or "unknown")
        by_priority[priority] = by_priority.get(priority, 0) + 1
    highest = ""
    if by_priority:
        highest = sorted(
            by_priority,
            key=lambda item: (priority_order.get(item, 99), item),
        )[0]
    return {
        "attention_required": bool(actions),
        "blocking_attention": any(str(action.get("priority")) in {"P0", "P1"} for action in actions),
        "count": len(actions),
        "by_priority": by_priority,
        "highest_priority": highest,
    }


def write_report(checks: list[Check], path: Path) -> None:
    next_actions = build_next_actions(checks)
    action_summary = summarize_next_actions(next_actions)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(ROOT),
        "ok": all(check.ok for check in checks),
        "attention_required": action_summary["attention_required"],
        "action_summary": action_summary,
        "checks": [asdict(check) for check in checks],
        "next_actions": next_actions,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily foundation health check.")
    parser.add_argument(
        "--json-out",
        default=str(ROOT / "reports" / "foundation_health_latest.json"),
        help="Write a JSON report to this path.",
    )
    parser.add_argument(
        "--browser-smoke",
        choices=("auto", "required", "off"),
        default="auto",
        help=(
            "Run the headless /chat_shell browser smoke gate. "
            "'auto' skips only when no Chromium browser is installed; 'required' fails hard."
        ),
    )
    args = parser.parse_args()

    checks = collect_checks(browser_smoke=args.browser_smoke)
    report_path = Path(args.json_out)
    write_report(checks, report_path)

    print("== Foundation Health Check ==")
    print(f"workspace: {ROOT}")
    print(f"report: {report_path}")
    for check in checks:
        mark = "OK" if check.ok else "FAIL"
        print(f"[{mark}] {check.name}: {check.status}")
    next_actions = build_next_actions(checks)
    if next_actions:
        action_summary = summarize_next_actions(next_actions)
        print(
            "attention_required: "
            f"yes highest={action_summary['highest_priority']} count={action_summary['count']}"
        )
        print("next actions:")
        for item in next_actions[:8]:
            print(f"- [{item['priority']}] {item['source']}: {item['summary']}")
        if len(next_actions) > 8:
            print(f"... {len(next_actions) - 8} more action(s) in the JSON report")
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    ]
    forbidden_tokens = [
        "http://127.0.0.1:7861/ingest/",
        "/static/branding/topbar-logo.png",
    ]
    missing = [token for token in required_tokens if token not in html]
    forbidden = [token for token in forbidden_tokens if token in html]
    ok = not missing and not forbidden
    return Check(
        "frontend_static_contract",
        ok,
        "ready" if ok else "contract_drift",
        {"path": str(template), "missing": missing, "forbidden": forbidden},
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
        "core/knowledge_hub.py",
        "core/workflow_runtime.py",
        "core/langgraph_workflow.py",
        "tools/foundation_health_check.py",
        "tools/chat_shell_browser_smoke.py",
        "tools/n8n_workflow_preflight.py",
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
        check_ports(),
        check_gateway(),
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


def write_report(checks: list[Check], path: Path) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(ROOT),
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
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
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

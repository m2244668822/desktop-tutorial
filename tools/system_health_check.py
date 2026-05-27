#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PROJECT_DIR = (
    Path(__file__).resolve().parents[1] / ".sync_user_project"
)

def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
            continue
        values[m.group(1)] = m.group(2).strip()
    return values


def as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def is_placeholder_secret(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    markers = [
        "your_openai_api_key_here",
        "your_huggingface_api_key_here",
        "your_together_api_key_here",
        "your_openrouter_api_key_here",
        "your_groq_api_key_here",
        "your_zzz_api_key_here",
        "your_gemini_api_key_here",
        "your_",
        "placeholder",
    ]
    return any(marker in text for marker in markers)


def key_format_ok(provider: str, value: str) -> bool:
    provider = provider.lower()
    if provider == "gemini":
        return value.startswith("AIza") and len(value) >= 35
    if provider == "nvidia":
        return value.startswith("nvapi-") and len(value) >= 24
    if provider in {"zzz", "zhizengzeng"}:
        return len(value) >= 20
    if provider == "huggingface":
        return value.startswith("hf_") and len(value) >= 20
    if provider == "openai":
        return value.startswith("sk-") and len(value) >= 20
    if provider == "groq":
        return value.startswith("gsk_") and len(value) >= 20
    if provider == "openrouter":
        return len(value) >= 20
    if provider == "together":
        return len(value) >= 20
    return len(value) > 0


def http_json(
    base_url: str, path: str, timeout: int = 20, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    req = Request(url, method="GET", headers=headers or {})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
            data = json.loads(payload) if payload else None
            return {"ok": True, "status": resp.status, "data": data, "error": ""}
    except HTTPError as exc:
        body = ""
        data = None
        try:
            body = exc.read().decode("utf-8")
            data = json.loads(body) if body else None
        except Exception:
            pass
        return {
            "ok": False,
            "status": exc.code,
            "data": data,
            "error": body or str(exc),
        }
    except URLError as exc:
        return {"ok": False, "status": 0, "data": None, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": 0, "data": None, "error": str(exc)}


def detect_listening_process(port: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "port": port,
        "listening": False,
        "pid": None,
        "cwd": "",
        "error": "",
    }
    try:
        cmd = ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            return result
        pid = None
        for line in proc.stdout.splitlines():
            if line.startswith("p"):
                pid = line[1:].strip()
                break
        if not pid:
            return result
        result["listening"] = True
        result["pid"] = int(pid)

        cwd_proc = subprocess.run(
            ["lsof", "-a", "-p", pid, "-d", "cwd"],
            check=False,
            capture_output=True,
            text=True,
        )
        if cwd_proc.returncode == 0:
            lines = cwd_proc.stdout.splitlines()
            if len(lines) >= 2:
                cols = re.split(r"\s+", lines[1].strip())
                if cols:
                    result["cwd"] = cols[-1]
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        return result


def load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def normalize_lsof_path(raw_path: str | None) -> str:
    value = str(raw_path or "").strip()
    if not value:
        return ""
    if "\\x" not in value:
        return value
    try:
        step1 = value.encode("utf-8").decode("unicode_escape")
        step2 = step1.encode("latin1").decode("utf-8")
        return step2
    except Exception:
        return value


def save_history(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(items[-50:], ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_key_checks(env: dict[str, str]) -> list[dict[str, Any]]:
    specs = [
        ("OPENAI_API_KEY", "openai", False),
        ("OPENROUTER_API_KEY", "openrouter", False),
        ("OPENROUTER_API_KEY_2", "openrouter", False),
        ("GROQ_API_KEY", "groq", False),
        (
            "GEMINI_API_KEY",
            "gemini",
            as_bool(env.get("GEMINI_REQUIRE_ENCRYPTED_KEY"), True),
        ),
        (
            "NVIDIA_API_KEY",
            "nvidia",
            as_bool(env.get("NVIDIA_REQUIRE_ENCRYPTED_KEY"), False),
        ),
        ("ZZZ_API_KEY", "zzz", as_bool(env.get("ZZZ_REQUIRE_ENCRYPTED_KEY"), True)),
        ("HF_API_KEY", "huggingface", False),
        ("TOGETHER_API_KEY", "together", False),
    ]

    checks: list[dict[str, Any]] = []
    for name, provider, require_enc in specs:
        plain = (env.get(name) or "").strip()
        enc = (env.get(f"{name}_ENC") or "").strip()

        if not plain:
            plain_state = "missing"
        elif is_placeholder_secret(plain):
            plain_state = "placeholder"
        elif not key_format_ok(provider, plain):
            plain_state = "format_invalid"
        else:
            plain_state = "ok"

        checks.append(
            {
                "name": name,
                "provider": provider,
                "plain_state": plain_state,
                "plain_present": bool(plain),
                "enc_present": bool(enc),
                "require_encrypted": bool(require_enc),
                "effective_ready": bool(enc)
                if require_enc
                else (plain_state == "ok" or bool(enc)),
            }
        )
    return checks


def summarize_api_availability(model_status: dict[str, Any]) -> list[dict[str, Any]]:
    model_choices = model_status.get("model_choices") or {}
    reasons = model_status.get("model_unavailable_reasons") or {}
    labels = [
        ("openai", "OpenAI"),
        ("openrouter", "OpenRouter"),
        ("groq", "Groq"),
        ("gemini", "Gemini"),
        ("nvidia", "NVIDIA"),
        ("zhizengzeng", "ZZZ"),
        ("huggingface", "HuggingFace"),
        ("together", "Together"),
        ("tinyllama", "Ollama/TinyLlama"),
        ("gpt2", "GPT-2"),
    ]
    result: list[dict[str, Any]] = []
    for key, label in labels:
        enabled = bool(model_choices.get(key))
        reason = str(reasons.get(key) or "").strip()
        result.append(
            {"key": key, "label": label, "enabled": enabled, "reason": reason}
        )
    return result


def fmt_bool(value: bool) -> str:
    return "ON" if value else "OFF"


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=== System Health Check ===")
    lines.append(f"Checked At: {report['checked_at']}")
    lines.append(f"Project: {report['project_dir']}")
    lines.append(f"Base URL: {report['base_url']}")
    lines.append("")

    score = report.get("security_score") or {}
    delta = report.get("security_delta")
    delta_text = "N/A" if delta is None else (f"{delta:+d}")
    lines.append(
        f"Security Score: {score.get('security_index', 'N/A')} ({score.get('grade', '?')})  delta={delta_text}"
    )
    lines.append(f"Risk Level: {score.get('risk_level', 'N/A')}")
    lines.append("")

    process = report.get("process") or {}
    lines.append("[Runtime]")
    lines.append(
        f"- Server Health: {report.get('server_health_status')} (HTTP {report.get('server_health_http_status')})"
    )
    lines.append(f"- Port Listening: {fmt_bool(bool(process.get('listening')))}")
    if process.get("pid"):
        lines.append(f"- PID: {process.get('pid')}")
    if process.get("cwd"):
        lines.append(f"- Process CWD: {process.get('cwd')}")
    lines.append(
        f"- CWD Matches Expected: {fmt_bool(bool(report.get('process_cwd_matches_expected')))}"
    )
    lines.append("")

    modes = report.get("modes") or {}
    lines.append("[Modes]")
    lines.append(f"- PRIVACY_MODE: {fmt_bool(bool(modes.get('privacy_mode')))}")
    lines.append(f"- LEARNING_MODE: {fmt_bool(bool(modes.get('learning_mode')))}")
    lines.append(f"- ASK_BACK_MODE: {fmt_bool(bool(modes.get('ask_back_mode')))}")
    lines.append(f"- KEY_FAIL_CLOSED: {fmt_bool(bool(modes.get('key_fail_closed')))}")
    lines.append("")

    auth = report.get("server_api_auth") or {}
    sync = report.get("sync") or {}
    lines.append("[Sync + Auth]")
    lines.append(f"- SERVER_API_TOKEN_REQUIRED: {fmt_bool(bool(auth.get('required')))}")
    lines.append(
        f"- SERVER_API_TOKEN Configured: {fmt_bool(bool(auth.get('token_configured')))}"
    )
    lines.append(
        f"- Protected Endpoint With Token: HTTP {report.get('protected_check_with_token_http')}"
    )
    lines.append(
        f"- Protected Endpoint Without Token: HTTP {report.get('protected_check_without_token_http')}"
    )
    lines.append(
        f"- Full Sync Async Default: {fmt_bool(bool(sync.get('full_sync_async_default')))}"
    )
    lines.append(
        f"- Full Sync API Timeout: {sync.get('full_sync_api_timeout_seconds')}s"
    )
    lines.append(
        f"- Full Sync Hard Timeout: {sync.get('full_sync_hard_timeout_seconds')}s"
    )
    lines.append(f"- Full Sync Active Jobs: {sync.get('full_sync_active_jobs')}")
    lines.append(
        f"- Last Full Sync: {sync.get('full_sync_last_status')} @ {sync.get('full_sync_last_at')}"
    )
    lines.append("")

    lines.append("[API Availability]")
    for item in report.get("api_availability", []):
        state = "OK" if item.get("enabled") else "NO"
        reason = item.get("reason") or ""
        suffix = f" | {reason}" if reason else ""
        lines.append(f"- {item.get('label')}: {state}{suffix}")
    lines.append("")

    lines.append("[Key Format + ENC]")
    for item in report.get("key_checks", []):
        lines.append(
            f"- {item['name']}: plain={item['plain_state']} enc={fmt_bool(item['enc_present'])} "
            f"require_enc={fmt_bool(item['require_encrypted'])} ready={fmt_bool(item['effective_ready'])}"
        )
    lines.append("")

    findings = report.get("top_findings", [])
    lines.append("[Top Findings]")
    if not findings:
        lines.append("- none")
    else:
        for f in findings:
            lines.append(f"- ({f.get('severity')}) {f.get('type')}: {f.get('message')}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-shot system health check for current AI workspace"
    )
    parser.add_argument(
        "--project-dir", default=str(DEFAULT_PROJECT_DIR)
    )
    parser.add_argument("--base-url", default="")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    env_path = project_dir / ".env"
    env_values = parse_env_file(env_path)

    port = int(env_values.get("CHAT_SERVER_PORT", "5001") or "5001")
    base_url = args.base_url.strip() or f"http://127.0.0.1:{port}"

    process_info = detect_listening_process(port)
    process_info["cwd"] = normalize_lsof_path(process_info.get("cwd"))
    expected_cwd = str(project_dir)
    cwd_matches_expected = (
        bool(process_info.get("cwd")) and str(process_info.get("cwd")) == expected_cwd
    )

    health_resp = http_json(base_url, "/health", timeout=args.timeout)
    model_resp = http_json(base_url, "/system/model-status", timeout=args.timeout)
    security_resp = http_json(base_url, "/system/security-status", timeout=args.timeout)
    bridge_resp = http_json(
        base_url, "/system/chatgpt-bridge/status", timeout=args.timeout
    )
    auth_resp = http_json(
        base_url, "/system/server-api-auth-status", timeout=args.timeout
    )

    server_api_token = (env_values.get("SERVER_API_TOKEN") or "").strip()
    with_token_headers = (
        {"Authorization": f"Bearer {server_api_token}"} if server_api_token else {}
    )
    protected_with_token = http_json(
        base_url,
        "/sync/full-sync/jobs?limit=1",
        timeout=args.timeout,
        headers=with_token_headers,
    )
    protected_without_token = http_json(
        base_url, "/sync/full-sync/jobs?limit=1", timeout=args.timeout, headers={}
    )

    model_data = model_resp.get("data") if model_resp.get("ok") else {}
    bridge_data = bridge_resp.get("data") if bridge_resp.get("ok") else {}
    auth_data = auth_resp.get("data") if auth_resp.get("ok") else {}

    key_checks = build_key_checks(env_values)
    api_availability = summarize_api_availability(
        model_data if isinstance(model_data, dict) else {}
    )

    security_data = security_resp.get("data") if security_resp.get("ok") else {}
    security_index = int((security_data or {}).get("security_index") or 0)
    grade = str((security_data or {}).get("grade") or "?")
    risk_level = str((security_data or {}).get("risk_level") or "unknown")
    findings = list((security_data or {}).get("findings") or [])

    history_path = project_dir / "instance" / "health_score_history.json"
    history = load_history(history_path)
    previous_score = history[-1].get("security_index") if history else None
    delta = (
        (security_index - int(previous_score))
        if isinstance(previous_score, int)
        else None
    )

    history.append(
        {
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "security_index": security_index,
            "grade": grade,
            "risk_level": risk_level,
        }
    )
    save_history(history_path, history)

    report: dict[str, Any] = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "project_dir": str(project_dir),
        "base_url": base_url,
        "server_health_status": (
            (health_resp.get("data") or {}).get("status")
            if isinstance(health_resp.get("data"), dict)
            else "unreachable"
        ),
        "server_health_http_status": health_resp.get("status"),
        "process": process_info,
        "process_cwd_matches_expected": cwd_matches_expected,
        "modes": {
            "privacy_mode": bool(
                (bridge_data or {}).get(
                    "privacy_mode", as_bool(env_values.get("PRIVACY_MODE"), False)
                )
            ),
            "learning_mode": bool(
                (bridge_data or {}).get(
                    "learning_mode", as_bool(env_values.get("LEARNING_MODE"), True)
                )
            ),
            "ask_back_mode": bool(
                (bridge_data or {}).get(
                    "ask_back_mode", as_bool(env_values.get("ASK_BACK_MODE"), True)
                )
            ),
            "key_fail_closed": bool(
                (bridge_data or {}).get(
                    "key_fail_closed", as_bool(env_values.get("KEY_FAIL_CLOSED"), True)
                )
            ),
        },
        "server_api_auth": {
            "required": bool((auth_data or {}).get("required")),
            "token_configured": bool((auth_data or {}).get("token_configured")),
            "ip_allowlist_enabled": bool((auth_data or {}).get("ip_allowlist_enabled")),
            "ip_allowlist_entries_count": int(
                (auth_data or {}).get("ip_allowlist_entries_count") or 0
            ),
        },
        "protected_check_with_token_http": protected_with_token.get("status"),
        "protected_check_without_token_http": protected_without_token.get("status"),
        "sync": {
            "full_sync_async_default": bool(
                (bridge_data or {}).get("full_sync_async_default")
            ),
            "full_sync_api_timeout_seconds": (bridge_data or {}).get(
                "full_sync_api_timeout_seconds"
            ),
            "full_sync_hard_timeout_seconds": (bridge_data or {}).get(
                "full_sync_hard_timeout_seconds"
            ),
            "full_sync_active_jobs": (bridge_data or {}).get("full_sync_active_jobs"),
            "full_sync_last_status": (bridge_data or {}).get("full_sync_last_status"),
            "full_sync_last_at": (bridge_data or {}).get("full_sync_last_at"),
            "full_sync_last_message": (bridge_data or {}).get("full_sync_last_message"),
            "ingest_require_token": bool(
                (bridge_data or {}).get("ingest_require_token")
            ),
        },
        "api_availability": api_availability,
        "key_checks": key_checks,
        "security_score": {
            "security_index": security_index,
            "grade": grade,
            "risk_level": risk_level,
        },
        "security_delta": delta,
        "top_findings": sorted(
            findings,
            key=lambda item: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                str(item.get("severity", "low")).lower(), 9
            ),
        )[:8],
        "raw_http": {
            "health": {
                "ok": health_resp.get("ok"),
                "status": health_resp.get("status"),
                "error": health_resp.get("error"),
            },
            "model_status": {
                "ok": model_resp.get("ok"),
                "status": model_resp.get("status"),
                "error": model_resp.get("error"),
            },
            "security_status": {
                "ok": security_resp.get("ok"),
                "status": security_resp.get("status"),
                "error": security_resp.get("error"),
            },
            "bridge_status": {
                "ok": bridge_resp.get("ok"),
                "status": bridge_resp.get("status"),
                "error": bridge_resp.get("error"),
            },
            "server_api_auth_status": {
                "ok": auth_resp.get("ok"),
                "status": auth_resp.get("status"),
                "error": auth_resp.get("error"),
            },
            "sync_jobs_with_token": {
                "ok": protected_with_token.get("ok"),
                "status": protected_with_token.get("status"),
                "error": protected_with_token.get("error"),
            },
            "sync_jobs_without_token": {
                "ok": protected_without_token.get("ok"),
                "status": protected_without_token.get("status"),
                "error": protected_without_token.get("error"),
            },
        },
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))

    # Non-zero exit only when core server health is down.
    if not health_resp.get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

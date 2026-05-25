#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT_DIR / ".sync_user_project" / ".env"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not match:
            continue

        key = match.group(1)
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def short_text(value: Any, limit: int = 80) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fmt_runtime(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def iso_to_local(iso_text: Any) -> str:
    raw = str(iso_text or "").strip()
    if not raw:
        return "-"
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%m-%d %H:%M:%S")
    except Exception:
        return short_text(raw, 19)


def http_json(
    base_url: str,
    path: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    request = Request(url, method="GET", headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload) if payload else None
            return {
                "ok": True,
                "status": int(response.status),
                "data": data,
                "error": "",
            }
    except HTTPError as exc:
        body = ""
        data = None
        try:
            body = exc.read().decode("utf-8")
            data = json.loads(body) if body else None
        except Exception:
            body = body or str(exc)
        return {
            "ok": False,
            "status": int(getattr(exc, "code", 0) or 0),
            "data": data,
            "error": short_text(body or str(exc), 220),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": 0,
            "data": None,
            "error": short_text(str(exc), 220),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": 0,
            "data": None,
            "error": short_text(str(exc), 220),
        }


@dataclass
class MonitorState:
    start_epoch: float = field(default_factory=time.time)
    cycle: int = 0
    events: deque[str] = field(default_factory=lambda: deque(maxlen=40))
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_notification_id: int = 0
    last_unresolved_count: int | None = None
    last_status_counts: dict[str, int] = field(default_factory=dict)
    last_trace_id: str = ""
    last_transport_state: str = ""
    last_full_status: str = ""
    last_semi_status: str = ""


def push_event(state: MonitorState, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    state.events.appendleft(f"{timestamp} | {message}")


def choose_value(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def resolve_base_url(args: argparse.Namespace, env_values: dict[str, str]) -> str:
    base = choose_value(
        args.base_url,
        os.getenv("CHATGPT_SERVER_BASE_URL"),
        os.getenv("SERVER_BASE_URL"),
        env_values.get("CHATGPT_SERVER_BASE_URL"),
        env_values.get("SERVER_BASE_URL"),
        "http://127.0.0.1:5001",
    )
    return base.rstrip("/")


def resolve_token(args: argparse.Namespace, env_values: dict[str, str]) -> str:
    return choose_value(
        args.token,
        os.getenv("SERVER_API_TOKEN"),
        os.getenv("SECRET_CODE"),
        env_values.get("SERVER_API_TOKEN"),
        env_values.get("SECRET_CODE"),
    )


def collect_snapshot(
    args: argparse.Namespace,
    state: MonitorState,
    base_url: str,
    auth_headers: dict[str, str],
) -> dict[str, Any]:
    started = time.time()
    endpoints: dict[str, dict[str, Any]] = {}

    core_specs = [
        ("health", "/health", False),
        ("cns_status", "/system/cns/status", False),
        ("bridge_status", "/system/chatgpt-bridge/status", False),
        ("tasks_summary", "/agent/tasks/summary", False),
        (
            "notifications",
            f"/agent/notifications?limit={args.notification_limit}",
            False,
        ),
    ]
    extended_specs = [
        ("runtime_strategy", "/system/runtime-strategy", False),
        ("data_framework", "/system/data-framework", False),
        (
            "latest_sync",
            "/system/chatgpt-bridge/latest-sync?history_limit=3&trace_limit=8",
            True,
        ),
        ("trace_latest", "/trace/latest?limit=12", True),
    ]

    refresh_extended = (
        state.cycle == 1
        or args.extended_every <= 1
        or state.cycle % args.extended_every == 0
    )

    def fetch(name: str, path: str, need_auth: bool) -> dict[str, Any]:
        headers = dict(auth_headers) if need_auth else {}
        response = http_json(
            base_url=base_url, path=path, timeout=args.timeout, headers=headers
        )
        response["path"] = path
        response["need_auth"] = need_auth
        response["stale"] = False
        return response

    for name, path, need_auth in core_specs:
        endpoints[name] = fetch(name, path, need_auth)

    for name, path, need_auth in extended_specs:
        if refresh_extended or name not in state.cache:
            latest = fetch(name, path, need_auth)
            state.cache[name] = latest
            endpoints[name] = latest
        else:
            cached = dict(state.cache[name])
            cached["stale"] = True
            endpoints[name] = cached

    return {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "poll_seconds": round(time.time() - started, 3),
        "endpoints": endpoints,
    }


def endpoint_data(snapshot: dict[str, Any], name: str, default: Any) -> Any:
    endpoint = (snapshot.get("endpoints") or {}).get(name) or {}
    if endpoint.get("ok"):
        data = endpoint.get("data")
        return data if data is not None else default
    return default


def latest_trace_item(snapshot: dict[str, Any]) -> dict[str, Any]:
    trace_data = endpoint_data(snapshot, "trace_latest", {}) or {}
    if isinstance(trace_data, dict) and isinstance(trace_data.get("latest"), dict):
        return trace_data.get("latest") or {}

    latest_sync_data = endpoint_data(snapshot, "latest_sync", {}) or {}
    trace_section = (
        latest_sync_data.get("trace") if isinstance(latest_sync_data, dict) else {}
    )
    if isinstance(trace_section, dict) and isinstance(
        trace_section.get("latest"), dict
    ):
        return trace_section.get("latest") or {}
    return {}


def bridge_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    latest_sync_data = endpoint_data(snapshot, "latest_sync", {}) or {}
    if isinstance(latest_sync_data, dict) and isinstance(
        latest_sync_data.get("bridge"), dict
    ):
        return latest_sync_data.get("bridge") or {}
    return endpoint_data(snapshot, "bridge_status", {}) or {}


def bridge_transport(snapshot: dict[str, Any]) -> dict[str, Any]:
    latest_sync_data = endpoint_data(snapshot, "latest_sync", {}) or {}
    if isinstance(latest_sync_data, dict) and isinstance(
        latest_sync_data.get("transport"), dict
    ):
        return latest_sync_data.get("transport") or {}
    return {}


def update_deltas(state: MonitorState, snapshot: dict[str, Any]) -> None:
    tasks = endpoint_data(snapshot, "tasks_summary", {}) or {}
    unresolved_count = tasks.get("unresolved_count")
    status_counts = (
        tasks.get("status_counts")
        if isinstance(tasks.get("status_counts"), dict)
        else {}
    )

    if isinstance(unresolved_count, int):
        if state.last_unresolved_count is None:
            state.last_unresolved_count = unresolved_count
        elif unresolved_count != state.last_unresolved_count:
            delta = unresolved_count - state.last_unresolved_count
            sign = "+" if delta > 0 else ""
            push_event(
                state,
                f"unresolved tasks {state.last_unresolved_count} -> {unresolved_count} ({sign}{delta})",
            )
            state.last_unresolved_count = unresolved_count

    normalized_counts = {
        str(key): as_int(value) for key, value in status_counts.items()
    }
    if state.last_status_counts and normalized_counts != state.last_status_counts:
        keys = sorted(
            set(state.last_status_counts.keys()) | set(normalized_counts.keys())
        )
        changes: list[str] = []
        for key in keys:
            old_value = state.last_status_counts.get(key, 0)
            new_value = normalized_counts.get(key, 0)
            if old_value != new_value:
                changes.append(f"{key}:{old_value}->{new_value}")
        if changes:
            push_event(state, "status counts changed " + ", ".join(changes[:4]))
    if normalized_counts:
        state.last_status_counts = normalized_counts

    notifications = endpoint_data(snapshot, "notifications", []) or []
    if isinstance(notifications, list) and notifications:
        max_id = max(
            as_int(item.get("notification_id"), 0)
            for item in notifications
            if isinstance(item, dict)
        )
        if state.last_notification_id <= 0:
            state.last_notification_id = max_id
        elif max_id > state.last_notification_id:
            fresh = [
                item
                for item in notifications
                if isinstance(item, dict)
                and as_int(item.get("notification_id"), 0) > state.last_notification_id
            ]
            for item in fresh[-4:]:
                notification_id = as_int(item.get("notification_id"), 0)
                level = str(item.get("level") or "info").lower()
                title = short_text(item.get("title"), 36)
                message = short_text(item.get("message"), 56)
                push_event(
                    state,
                    f"notification#{notification_id} [{level}] {title} | {message}",
                )
            state.last_notification_id = max_id

    latest_trace = latest_trace_item(snapshot)
    trace_id = str(latest_trace.get("trace_id") or "").strip()
    if trace_id:
        if state.last_trace_id and trace_id != state.last_trace_id:
            ack = (
                latest_trace.get("ack")
                if isinstance(latest_trace.get("ack"), dict)
                else {}
            )
            ack_status = ack.get("status")
            latency = latest_trace.get("latency") or ack.get("elapsed_ms")
            push_event(
                state,
                f"new trace {trace_id} ack={ack_status if ack_status is not None else '-'} latency={latency if latency is not None else '-'}ms",
            )
        state.last_trace_id = trace_id

    bridge = bridge_payload(snapshot)
    full_status = str(bridge.get("full_sync_last_status") or "").strip().lower()
    semi_status = str(bridge.get("semi_full_sync_last_status") or "").strip().lower()
    if full_status:
        if state.last_full_status and full_status != state.last_full_status:
            push_event(
                state, f"full sync status {state.last_full_status} -> {full_status}"
            )
        state.last_full_status = full_status
    if semi_status:
        if state.last_semi_status and semi_status != state.last_semi_status:
            push_event(
                state,
                f"semi-full sync status {state.last_semi_status} -> {semi_status}",
            )
        state.last_semi_status = semi_status

    transport = bridge_transport(snapshot)
    transport_state = str(transport.get("state") or "").strip().lower()
    if transport_state:
        if state.last_transport_state and transport_state != state.last_transport_state:
            push_event(
                state,
                f"bridge transport {state.last_transport_state} -> {transport_state}",
            )
        state.last_transport_state = transport_state


def gather_issues(snapshot: dict[str, Any]) -> list[str]:
    endpoints = snapshot.get("endpoints") or {}
    issues: list[str] = []

    for name, endpoint in endpoints.items():
        if endpoint.get("ok"):
            continue
        status = endpoint.get("status")
        error = short_text(endpoint.get("error"), 120)
        marker = "cached" if endpoint.get("stale") else "live"
        issues.append(f"{name} [{marker}] HTTP {status}: {error}")

    health = endpoint_data(snapshot, "health", {}) or {}
    database = (
        health.get("database") if isinstance(health.get("database"), dict) else {}
    )
    if health.get("status") not in {"ok", None}:
        issues.append(f"health degraded: status={health.get('status')}")
    if database and not bool(database.get("ok", True)):
        issues.append(f"database not ok: {short_text(database.get('error'), 100)}")

    tasks = endpoint_data(snapshot, "tasks_summary", {}) or {}
    status_counts = (
        tasks.get("status_counts")
        if isinstance(tasks.get("status_counts"), dict)
        else {}
    )
    failed_count = as_int(status_counts.get("failed"), 0)
    running_count = as_int(status_counts.get("running"), 0)
    if failed_count > 0:
        issues.append(f"failed tasks: {failed_count}")
    if running_count > 0:
        issues.append(f"running tasks: {running_count}")

    latest_trace = latest_trace_item(snapshot)
    if latest_trace:
        ack = (
            latest_trace.get("ack") if isinstance(latest_trace.get("ack"), dict) else {}
        )
        ack_status = ack.get("status")
        if isinstance(ack_status, int) and ack_status >= 400:
            issues.append(
                f"latest trace ack failed: trace={latest_trace.get('trace_id')} status={ack_status}"
            )
        if str(latest_trace.get("status") or "").lower() in {
            "error",
            "failed",
            "timeout",
        }:
            issues.append(
                "latest trace status="
                + short_text(latest_trace.get("status"), 24)
                + f" trace={short_text(latest_trace.get('trace_id'), 20)}"
            )

    bridge = bridge_payload(snapshot)
    for key in ("full_sync_last_status", "semi_full_sync_last_status"):
        value = str(bridge.get(key) or "").strip().lower()
        if value in {"failed", "error", "timeout"}:
            issues.append(f"{key}={value}")

    transport = bridge_transport(snapshot)
    transport_state = str(transport.get("state") or "").strip().lower()
    if transport_state in {"error", "read_error", "missing_log"}:
        issues.append(
            f"bridge transport state={transport_state}: {short_text(transport.get('summary'), 100)}"
        )

    notifications = endpoint_data(snapshot, "notifications", []) or []
    if isinstance(notifications, list):
        for item in notifications[-6:]:
            if not isinstance(item, dict):
                continue
            level = str(item.get("level") or "").strip().lower()
            if level in {"error", "warning", "critical"}:
                issues.append(
                    f"notification#{as_int(item.get('notification_id'))} [{level}] "
                    + short_text(item.get("title"), 42)
                )

    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        normalized = issue.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def print_endpoint_line(name: str, endpoint: dict[str, Any]) -> None:
    mode = "cached" if endpoint.get("stale") else "live"
    if endpoint.get("ok"):
        print(f"  - {name:14s} : ok ({mode})")
        return
    print(
        "  - "
        f"{name:14s} : fail ({mode}) HTTP {endpoint.get('status')} "
        f"{short_text(endpoint.get('error'), 80)}"
    )


def render(
    args: argparse.Namespace,
    state: MonitorState,
    snapshot: dict[str, Any],
    issues: list[str],
    token_loaded: bool,
    env_file: Path,
) -> None:
    if not args.no_clear:
        print("\033[2J\033[H", end="")

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed_text = fmt_runtime(time.time() - state.start_epoch)
    endpoints = snapshot.get("endpoints") or {}
    auth_state = "loaded" if token_loaded else "missing"

    print("=" * 96)
    print(
        f"Live Agent Monitor | {now_text} | cycle={state.cycle} | uptime={elapsed_text} | poll={snapshot.get('poll_seconds')}s"
    )
    print(
        f"base_url={args.base_url} | auth_token={auth_state} | interval={args.interval}s | extended_every={args.extended_every}"
    )
    print(f"env_file={env_file}")
    print("=" * 96)

    print("[Endpoint Status]")
    for name in [
        "health",
        "cns_status",
        "bridge_status",
        "tasks_summary",
        "notifications",
        "runtime_strategy",
        "data_framework",
        "latest_sync",
        "trace_latest",
    ]:
        print_endpoint_line(name, endpoints.get(name) or {})

    health = endpoint_data(snapshot, "health", {}) or {}
    runtime = endpoint_data(snapshot, "runtime_strategy", {}) or {}
    cns = endpoint_data(snapshot, "cns_status", {}) or {}
    bridge = bridge_payload(snapshot)
    transport = bridge_transport(snapshot)
    latest_trace = latest_trace_item(snapshot)
    tasks = endpoint_data(snapshot, "tasks_summary", {}) or {}
    notifications = endpoint_data(snapshot, "notifications", []) or []
    data_framework = endpoint_data(snapshot, "data_framework", {}) or {}

    print("\n[System]")
    db = health.get("database") if isinstance(health.get("database"), dict) else {}
    print(
        f"  health={health.get('status', '-')} | db_ok={db.get('ok', '-')} | health_ts={short_text(health.get('timestamp'), 24)}"
    )
    server_auth = (
        runtime.get("server_api_auth")
        if isinstance(runtime.get("server_api_auth"), dict)
        else {}
    )
    print(
        "  execution_provider="
        f"{runtime.get('execution_provider', '-')} | chat_provider={runtime.get('chat_preferred_provider', '-')}"
    )
    print(
        "  server_api_token_required="
        f"{server_auth.get('required', '-')} | token_configured={server_auth.get('token_configured', '-')}"
    )
    cns_runtime = cns.get("runtime") if isinstance(cns.get("runtime"), dict) else {}
    cns_last_summary = short_text(cns_runtime.get("last_cycle_summary"), 100)
    print(
        "  cns_enabled="
        f"{cns.get('enabled', '-')} | cns_interval={cns.get('interval_seconds', '-')}s | last_cycle={cns_last_summary or '-'}"
    )

    print("\n[Bridge / Sync]")
    print(
        "  full_sync="
        f"{bridge.get('full_sync_last_status', '-')} @ {iso_to_local(bridge.get('full_sync_last_at'))}"
        f" | active_jobs={bridge.get('full_sync_active_jobs', '-')}"
    )
    print(
        "  semi_full_sync="
        f"{bridge.get('semi_full_sync_last_status', '-')} @ {iso_to_local(bridge.get('semi_full_sync_last_at'))}"
        f" | active_jobs={bridge.get('semi_full_sync_active_jobs', '-')}"
    )
    print(
        "  transport_state="
        f"{transport.get('state', '-')} | summary={short_text(transport.get('summary'), 80)}"
    )
    ack = latest_trace.get("ack") if isinstance(latest_trace.get("ack"), dict) else {}
    trace_latency = latest_trace.get("latency")
    if trace_latency is None:
        trace_latency = ack.get("elapsed_ms")
    print(
        "  latest_trace="
        f"{latest_trace.get('trace_id', '-')} | trace_status={latest_trace.get('status', '-')}"
        f" | ack_status={ack.get('status', '-')} | latency_ms={trace_latency if trace_latency is not None else '-'}"
    )

    print("\n[Task Progress]")
    status_counts = (
        tasks.get("status_counts")
        if isinstance(tasks.get("status_counts"), dict)
        else {}
    )
    status_line = ", ".join(
        f"{name}={as_int(status_counts.get(name), 0)}"
        for name in ("pending", "running", "failed", "completed", "resolved", "skipped")
        if name in status_counts
    )
    print(
        f"  unresolved={tasks.get('unresolved_count', '-')} | {status_line or 'status_counts unavailable'}"
    )
    unresolved_items = (
        tasks.get("unresolved_items")
        if isinstance(tasks.get("unresolved_items"), list)
        else []
    )
    if not unresolved_items:
        print("  unresolved_items: none")
    else:
        print(f"  unresolved_items (top {args.task_limit}):")
        for item in unresolved_items[: args.task_limit]:
            if not isinstance(item, dict):
                continue
            task_id = item.get("task_id", "-")
            status = short_text(item.get("status"), 12)
            agent = short_text(item.get("assigned_agent"), 14)
            title = short_text(item.get("title"), 60)
            updated_at = iso_to_local(item.get("updated_at"))
            print(
                f"    - #{task_id} [{status}] {agent} | {title} | updated={updated_at}"
            )

    print("\n[Recent Notifications]")
    if not isinstance(notifications, list) or not notifications:
        print("  none")
    else:
        for item in notifications[-args.notification_limit :]:
            if not isinstance(item, dict):
                continue
            notification_id = as_int(item.get("notification_id"), 0)
            level = short_text(item.get("level"), 10)
            agent = short_text(item.get("agent_key"), 14)
            title = short_text(item.get("title"), 34)
            message = short_text(item.get("message"), 80)
            created_at = iso_to_local(item.get("created_at"))
            print(
                f"    - #{notification_id} [{level}] {agent} | {title} | {message} | at={created_at}"
            )

    print("\n[Data Link]")
    db_counts = (
        data_framework.get("database")
        if isinstance(data_framework.get("database"), dict)
        else {}
    )
    if db_counts:
        print(
            "  chat_history="
            f"{db_counts.get('chat_history_count', '-')} | tasks={db_counts.get('agent_task_count', '-')}"
            f" | signals={db_counts.get('agent_signal_count', '-')}"
            f" | heartbeats={db_counts.get('cns_heartbeat_count', '-')}"
            f" | notifications={db_counts.get('agent_notification_count', '-')}"
        )
    else:
        print("  database counts unavailable (endpoint missing or stale failure)")

    print("\n[Problems]")
    if not issues:
        print("  none")
    else:
        for issue in issues[: args.issue_limit]:
            print(f"  - {issue}")

    print("\n[Recent Events]")
    if not state.events:
        print("  (no changes detected yet)")
    else:
        for event in list(state.events)[: args.event_limit]:
            print(f"  - {event}")

    print("\nPress Ctrl+C to stop.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live terminal dashboard for agent workflow, sync status, and issues.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Server base URL. Default from env or http://127.0.0.1:5001",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to .env for SERVER_API_TOKEN and base URL",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Server API token (if omitted, auto-load from env/.env)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="Refresh interval in seconds",
    )
    parser.add_argument(
        "--extended-every",
        type=int,
        default=4,
        help="Refresh heavier endpoints every N cycles",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="HTTP timeout seconds per request",
    )
    parser.add_argument(
        "--task-limit",
        type=int,
        default=8,
        help="Show top N unresolved tasks",
    )
    parser.add_argument(
        "--notification-limit",
        type=int,
        default=8,
        help="Show latest N notifications",
    )
    parser.add_argument(
        "--event-limit",
        type=int,
        default=10,
        help="Show latest N change events",
    )
    parser.add_argument(
        "--issue-limit",
        type=int,
        default=10,
        help="Show latest N issues",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear terminal each refresh",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle and exit",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser().resolve()
    env_values = parse_env_file(env_file)
    args.base_url = resolve_base_url(args, env_values)

    token = resolve_token(args, env_values)
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    state = MonitorState()

    try:
        while True:
            cycle_start = time.time()
            state.cycle += 1

            snapshot = collect_snapshot(
                args=args,
                state=state,
                base_url=args.base_url,
                auth_headers=auth_headers,
            )
            update_deltas(state, snapshot)
            issues = gather_issues(snapshot)
            render(
                args=args,
                state=state,
                snapshot=snapshot,
                issues=issues,
                token_loaded=bool(token),
                env_file=env_file,
            )

            if args.once:
                return 0

            elapsed = time.time() - cycle_start
            sleep_seconds = max(0.0, args.interval - elapsed)
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

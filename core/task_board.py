#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task board payload helpers.

This module is intentionally read-only: it normalizes existing autonomy queue
files and workflow run logs into the JSON contract used by the web task board.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

STATUS_KEYS = ("pending", "running", "completed", "failed")
UNRESOLVED_STATUSES = {"pending", "running", "failed"}

STATUS_ALIASES = {
    "todo": "pending",
    "queued": "pending",
    "queue": "pending",
    "wait": "pending",
    "waiting": "pending",
    "open": "pending",
    "unresolved": "pending",
    "in_progress": "running",
    "in-progress": "running",
    "processing": "running",
    "active": "running",
    "started": "running",
    "done": "completed",
    "complete": "completed",
    "completed": "completed",
    "success": "completed",
    "succeeded": "completed",
    "ok": "completed",
    "failed": "failed",
    "fail": "failed",
    "failure": "failed",
    "error": "failed",
    "errored": "failed",
    "cancelled": "failed",
    "canceled": "failed",
}

ROUTE_AGENT_ALIASES = {
    "dispatcher": "dispatcher",
    "manager": "dispatcher",
    "general": "dispatcher",
    "orchestrator": "dispatcher",
    "engineering": "engineer",
    "engineer": "engineer",
    "dev": "engineer",
    "research": "researcher",
    "researcher": "researcher",
    "editor": "xiaobian",
    "xiaobian": "xiaobian",
    "content": "xiaobian",
    "prophet": "prophet",
    "proclaimer": "prophet",
    "security": "whitehat",
    "whitehat": "whitehat",
    "hat": "whitehat",
    "relay": "relay",
    "總管": "dispatcher",
    "通用": "dispatcher",
    "工程師": "engineer",
    "研究員": "researcher",
    "小編": "xiaobian",
    "申言者": "prophet",
    "帽子": "whitehat",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_text(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\x00", "").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _iso_timestamp(value: Any, fallback: float = 0.0) -> float:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return fallback


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def _normalize_status(raw: Any = "", *, failed_steps: Any = 0) -> str:
    failed_count = _safe_int(failed_steps, 0)
    text = str(raw or "").strip().lower().replace(" ", "_")
    if failed_count > 0 and text not in {"running", "in_progress", "processing"}:
        return "failed"
    if text in STATUS_KEYS:
        return text
    if text in STATUS_ALIASES:
        return STATUS_ALIASES[text]
    return "pending"


def _normalize_agent(route: Any) -> str:
    text = str(route or "").strip()
    lowered = text.lower().replace(" ", "_").replace("-", "_")
    return ROUTE_AGENT_ALIASES.get(lowered, "dispatcher")


def _queue_files(workspace_root: Path) -> list[Path]:
    root = Path(workspace_root).expanduser().resolve()
    candidates = [
        root / "data" / "autonomy" / "task_queue.json",
        root / "data_hdd_storage" / "autonomy" / "task_queue.json",
    ]
    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            result.append(path)
    return result


def _workflow_log_files(workspace_root: Path, max_workflow_logs: int = 500) -> list[Path]:
    logs_dir = Path(workspace_root).expanduser().resolve() / "logs" / "workflow_runs"
    if not logs_dir.is_dir():
        return []
    files = [p for p in logs_dir.glob("*.json") if p.is_file()]
    files.sort(key=_path_mtime, reverse=True)
    return files[:max(0, max_workflow_logs)]


def _item_key(item: dict[str, Any]) -> str:
    for name in ("task_id", "id", "trace_id"):
        value = _safe_text(item.get(name), 120)
        if value:
            return value
    return _safe_text(item.get("path"), 240)


def _merge_item(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    old_ts = _iso_timestamp(existing.get("updated_at") or existing.get("created_at"))
    new_ts = _iso_timestamp(incoming.get("updated_at") or incoming.get("created_at"))
    primary, secondary = (incoming, existing) if new_ts >= old_ts else (existing, incoming)
    merged = dict(secondary)
    merged.update({k: v for k, v in primary.items() if v not in (None, "", [])})
    sources = []
    for source in (existing.get("source"), incoming.get("source")):
        if source and source not in sources:
            sources.append(str(source))
    if sources:
        merged["source"] = ",".join(sources)
    return merged


def _queue_task_to_item(task: dict[str, Any], source_path: Path) -> dict[str, Any]:
    result_summary = task.get("result_summary") if isinstance(task.get("result_summary"), dict) else {}
    failed_steps = result_summary.get("failed_steps", 0)
    raw_status = task.get("status") or result_summary.get("overall_status")
    route = task.get("route") or task.get("assigned_agent") or task.get("agent")
    task_id = task.get("task_id") or task.get("id") or task.get("trace_id") or source_path.stem
    title = task.get("title") or task.get("input") or task.get("user_input") or task_id
    updated_at = task.get("updated_at") or task.get("finished_at") or task.get("created_at") or datetime.fromtimestamp(_path_mtime(source_path)).isoformat(timespec="seconds")
    return {
        "id": _safe_text(task.get("id") or task_id, 120),
        "task_id": _safe_text(task_id, 120),
        "trace_id": _safe_text(task.get("trace_id"), 120),
        "status": _normalize_status(raw_status, failed_steps=failed_steps),
        "title": _safe_text(title),
        "route": _safe_text(route, 80),
        "assigned_agent": _normalize_agent(route),
        "agent_label": _safe_text(route or _normalize_agent(route), 80),
        "priority": _safe_int(task.get("priority"), 0),
        "created_at": _safe_text(task.get("created_at") or updated_at, 80),
        "updated_at": _safe_text(updated_at, 80),
        "completed_steps": _safe_int(result_summary.get("completed_steps"), 0),
        "failed_steps": _safe_int(failed_steps, 0),
        "log_path": _safe_text(task.get("log_path"), 260),
        "source": "autonomy_queue",
        "path": str(source_path),
    }


def _workflow_payload_to_item(payload: dict[str, Any], source_path: Path) -> dict[str, Any]:
    state = payload.get("task_state") if isinstance(payload.get("task_state"), dict) else payload
    route = state.get("route") or payload.get("route") or state.get("assigned_agent")
    task_id = state.get("task_id") or payload.get("task_id") or source_path.stem
    trace_id = state.get("trace_id") or payload.get("trace_id")
    failed_steps = state.get("failed_steps", payload.get("failed_steps", 0))
    raw_status = state.get("status") or state.get("overall_status") or payload.get("overall_status")
    title = state.get("title") or state.get("user_input") or payload.get("user_input") or task_id
    created_at = payload.get("created_at") or state.get("created_at") or datetime.fromtimestamp(_path_mtime(source_path)).isoformat(timespec="seconds")
    updated_at = state.get("finished_at") or payload.get("finished_at") or state.get("updated_at") or created_at
    return {
        "id": _safe_text(task_id, 120),
        "task_id": _safe_text(task_id, 120),
        "trace_id": _safe_text(trace_id, 120),
        "status": _normalize_status(raw_status, failed_steps=failed_steps),
        "title": _safe_text(title),
        "route": _safe_text(route, 80),
        "assigned_agent": _normalize_agent(route),
        "agent_label": _safe_text(route or _normalize_agent(route), 80),
        "priority": _safe_int(state.get("priority"), 0),
        "created_at": _safe_text(created_at, 80),
        "updated_at": _safe_text(updated_at, 80),
        "completed_steps": _safe_int(state.get("completed_steps", payload.get("completed_steps", 0)), 0),
        "failed_steps": _safe_int(failed_steps, 0),
        "log_path": str(source_path),
        "source": "workflow_log",
        "path": str(source_path),
    }


def _regex_field(text: str, name: str) -> str:
    match = re.search(r'"' + re.escape(name) + r'"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text)
    if not match:
        return ""
    try:
        return json.loads('"' + match.group(1) + '"')
    except Exception:
        return match.group(1)


def _regex_int(text: str, name: str) -> int:
    match = re.search(r'"' + re.escape(name) + r'"\s*:\s*(-?\d+)', text)
    return _safe_int(match.group(1), 0) if match else 0


def _workflow_text_to_item(text: str, source_path: Path) -> dict[str, Any]:
    task_id = _regex_field(text, "task_id") or source_path.stem
    trace_id = _regex_field(text, "trace_id")
    route = _regex_field(text, "route")
    failed_steps = _regex_int(text, "failed_steps")
    raw_status = _regex_field(text, "overall_status") or _regex_field(text, "status")
    title = _regex_field(text, "user_input") or task_id
    created_at = _regex_field(text, "created_at") or datetime.fromtimestamp(_path_mtime(source_path)).isoformat(timespec="seconds")
    return {
        "id": _safe_text(task_id, 120),
        "task_id": _safe_text(task_id, 120),
        "trace_id": _safe_text(trace_id, 120),
        "status": _normalize_status(raw_status, failed_steps=failed_steps),
        "title": _safe_text(title),
        "route": _safe_text(route, 80),
        "assigned_agent": _normalize_agent(route),
        "agent_label": _safe_text(route or _normalize_agent(route), 80),
        "priority": 0,
        "created_at": _safe_text(created_at, 80),
        "updated_at": _safe_text(created_at, 80),
        "completed_steps": _regex_int(text, "completed_steps"),
        "failed_steps": failed_steps,
        "log_path": str(source_path),
        "source": "workflow_log_recovered",
        "path": str(source_path),
    }


def collect_task_items(workspace_root: str | Path, *, max_workflow_logs: int = 500) -> list[dict[str, Any]]:
    root = Path(workspace_root).expanduser().resolve()
    by_key: dict[str, dict[str, Any]] = {}

    for queue_path in _queue_files(root):
        payload = _read_json(queue_path)
        tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            item = _queue_task_to_item(task, queue_path)
            key = _item_key(item)
            by_key[key] = _merge_item(by_key[key], item) if key in by_key else item

    for log_path in _workflow_log_files(root, max_workflow_logs=max_workflow_logs):
        payload = _read_json(log_path)
        if isinstance(payload, dict):
            item = _workflow_payload_to_item(payload, log_path)
        else:
            text = _read_text(log_path)
            if not text:
                continue
            item = _workflow_text_to_item(text, log_path)
        key = _item_key(item)
        by_key[key] = _merge_item(by_key[key], item) if key in by_key else item

    items = list(by_key.values())
    items.sort(key=lambda item: _iso_timestamp(item.get("updated_at") or item.get("created_at")), reverse=True)
    return items


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key in STATUS_KEYS}
    for item in items:
        status = item.get("status") if item.get("status") in STATUS_KEYS else "pending"
        counts[str(status)] += 1
    return counts


def task_summary_payload(workspace_root: str | Path) -> dict[str, Any]:
    items = collect_task_items(workspace_root)
    counts = _status_counts(items)
    unresolved_count = sum(counts[key] for key in UNRESOLVED_STATUSES)
    return {
        "ok": True,
        "status_counts": counts,
        "unresolved_count": unresolved_count,
        "total": len(items),
        "updated_at": _now_iso(),
        "sources": [str(path) for path in _queue_files(Path(workspace_root))],
    }


def _sort_for_filter(items: list[dict[str, Any]], status_filter: str) -> list[dict[str, Any]]:
    normalized_filter = (status_filter or "").strip().lower()
    if normalized_filter == "unresolved":
        priority = {"running": 0, "failed": 1, "pending": 2, "completed": 3}
        return sorted(
            items,
            key=lambda item: (
                priority.get(str(item.get("status")), 9),
                -_iso_timestamp(item.get("updated_at") or item.get("created_at")),
            ),
        )
    return sorted(items, key=lambda item: _iso_timestamp(item.get("updated_at") or item.get("created_at")), reverse=True)


def _filter_items(items: list[dict[str, Any]], status_filter: str) -> list[dict[str, Any]]:
    normalized_filter = (status_filter or "").strip().lower()
    if normalized_filter in {"", "all"}:
        return items
    if normalized_filter == "unresolved":
        return [item for item in items if item.get("status") in UNRESOLVED_STATUSES]
    normalized_status = STATUS_ALIASES.get(normalized_filter, normalized_filter)
    if normalized_status not in STATUS_KEYS:
        return items
    return [item for item in items if item.get("status") == normalized_status]


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "id",
        "task_id",
        "trace_id",
        "status",
        "title",
        "route",
        "assigned_agent",
        "agent_label",
        "priority",
        "created_at",
        "updated_at",
        "completed_steps",
        "failed_steps",
        "source",
        "log_path",
    }
    return {key: value for key, value in item.items() if key in keep}


def task_items_payload(
    workspace_root: str | Path,
    *,
    status: str = "",
    limit: int = 30,
    compact: bool = False,
) -> dict[str, Any]:
    all_items = collect_task_items(workspace_root)
    filtered = _filter_items(all_items, status)
    filtered = _sort_for_filter(filtered, status)
    safe_limit = max(1, min(_safe_int(limit, 30), 500))
    page = filtered[:safe_limit]
    if compact:
        page = [_compact_item(item) for item in page]
    return {
        "ok": True,
        "items": page,
        "count": len(filtered),
        "total": len(all_items),
        "limit": safe_limit,
        "filter": status or "all",
        "status_counts": _status_counts(all_items),
        "updated_at": _now_iso(),
    }
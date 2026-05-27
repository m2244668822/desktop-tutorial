#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append a task into autonomy queue for daemon auto-execution."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]


def _resolve_data_root(base_dir: Path) -> Path:
    primary = base_dir / "data"
    fallback = base_dir / "data_hdd_storage"
    if primary.is_dir():
        return primary
    if fallback.is_dir():
        return fallback
    if primary.exists() and not primary.is_dir():
        return fallback
    return primary


QUEUE_FILE = _resolve_data_root(BASE_DIR) / "autonomy" / "task_queue.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enqueue autonomy task")
    p.add_argument("--route", default="總管", help="Agent route (default: 總管)")
    p.add_argument("--input", required=True, help="Task input text")
    p.add_argument("--priority", type=int, default=5, help="Task priority (lower is higher)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    payload = read_json(QUEUE_FILE, {"tasks": []})
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []

    task = {
        "id": f"aq-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "route": str(args.route),
        "input": str(args.input),
        "priority": int(args.priority),
        "status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    tasks.append(task)
    tasks.sort(key=lambda x: (int(x.get("priority", 5)), str(x.get("created_at", ""))))
    write_json(QUEUE_FILE, {"updated_at": now_iso(), "tasks": tasks})
    print(f"[autonomy] queued {task['id']} route={task['route']} priority={task['priority']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

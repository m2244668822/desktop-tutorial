#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小編持續學習循環：
1) 先同步 OOSchool 已登入頁面快照
2) 再觸發小編學習任務（本地 tinyllama 優先）
3) 以固定間隔持續執行
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_URL = "http://127.0.0.1:5001"


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[xiaobian-loop] {now_ts()} {message}", flush=True)


def http_json(
    method: str, url: str, payload: dict | None = None, timeout: int = 60
) -> dict:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url=url, method=method.upper(), data=body, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} {url}: {text[:320]}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error {url}: {exc}") from exc


def run_ooschool_sync(server_url: str) -> dict:
    cmd = [
        "python3",
        str(BASE_DIR / "tools" / "ooschool_live_sync.py"),
        "--server-url",
        server_url,
        "--print-json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise RuntimeError(f"ooschool sync failed: {stderr or stdout}")
    output = (proc.stdout or "").strip()
    if not output:
        raise RuntimeError("ooschool sync output empty")
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ooschool sync json parse failed: {output[:300]}") from exc


def run_xiaobian_learning_task(server_url: str) -> dict:
    payload = {
        "title": f"小編持續學習循環 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "description": "依最新 OOSchool 課程快照，更新完整學習矩陣並標記每門課交付與驗收進度。",
        "goals": "維持課程學習矩陣持續更新，確保可交付與可驗收。",
        "constraints": "課名必須與快照一致；輸出簡潔且可追蹤。",
        "output_format": "json_report",
        "model_hint": "tinyllama",
        "issue_tags": [
            "ooschool",
            "xiaobian_learning",
            "all_courses_required",
            "continuous_learning",
        ],
        "run_async": True,
    }
    return http_json(
        "POST",
        f"{server_url.rstrip('/')}/agent/xiaobian/task",
        payload=payload,
        timeout=180,
    )


def count_active_continuous_tasks(server_url: str) -> int:
    total = 0
    for status in ("running", "pending"):
        query = urlencode(
            {
                "assigned_agent": "xiaobian",
                "status": status,
                "limit": 100,
            }
        )
        payload = http_json(
            "GET", f"{server_url.rstrip('/')}/agent/tasks?{query}", timeout=30
        )
        items = payload.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            if title.startswith("小編持續學習循環"):
                total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run continuous xiaobian learning loop"
    )
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument(
        "--interval",
        type=int,
        default=900,
        help="Loop interval in seconds (default: 900)",
    )
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    interval = max(60, int(args.interval))

    if args.once:
        sync_summary = run_ooschool_sync(args.server_url)
        task_result = run_xiaobian_learning_task(args.server_url)
        task_row = (
            task_result.get("task")
            if isinstance(task_result.get("task"), dict)
            else task_result
        )
        log(
            "once completed "
            f"courses={sync_summary.get('course_count')} "
            f"task_id={task_row.get('task_id')} "
            f"status={task_row.get('status')} "
        )
        return 0

    log(f"continuous mode started interval={interval}s server={args.server_url}")
    while True:
        try:
            sync_summary = run_ooschool_sync(args.server_url)
            log(
                "sync ok "
                f"courses={sync_summary.get('course_count')} "
                f"snapshot={sync_summary.get('snapshot_path')}"
            )
            active_count = count_active_continuous_tasks(args.server_url)
            if active_count > 0:
                log(f"skip enqueue: active_continuous_tasks={active_count}")
                time.sleep(interval)
                continue
            task_result = run_xiaobian_learning_task(args.server_url)
            task_row = (
                task_result.get("task")
                if isinstance(task_result.get("task"), dict)
                else task_result
            )
            log(
                "learning task queued "
                f"task_id={task_row.get('task_id')} "
                f"status={task_row.get('status')}"
            )
        except KeyboardInterrupt:
            log("stopped by keyboard interrupt")
            return 0
        except Exception as exc:
            log(f"cycle error: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())

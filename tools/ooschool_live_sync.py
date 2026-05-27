#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從已登入的 Chrome OOSchool 課程頁即時抓取課程清單與進度，
並寫入 knowledge_hub 快照，必要時可自動補齊小編第二輪任務。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_URL = "http://127.0.0.1:5001"

ROUND2_TASK_TEMPLATES = [
    {
        "title": "小編第二輪深度學習：53課程進度排程",
        "agent_label": "xiaobian.learning.ooschool.round2.scheduler",
        "description": "根據 ooschool-page-live-snapshot 的課程與進度，輸出分階段學習排程（先有進度課，再補 0% 課）。",
        "goals": "輸出 4 週排程表、每週里程碑、每週可交付成果。",
        "constraints": "必須對應真實課名與當前進度百分比；不可抽象空話。",
        "issue_tags": [
            "meeting_action",
            "xiaobian_learning",
            "round2",
            "curriculum_scheduler",
            "knowledge_base",
            "priority_highest",
        ],
    },
    {
        "title": "小編第二輪深度學習：課程到模板映射",
        "agent_label": "xiaobian.learning.ooschool.round2.template_map",
        "description": "把課程映射為可重用輸出模板，至少涵蓋：視覺、插畫、影片、行銷、商業、Live2D。",
        "goals": "每個領域至少輸出 3 個模板（共 18+），每個模板含輸入欄位/輸出格式/品質檢核。",
        "constraints": "模板需直接可用於實務任務與協作交接。",
        "issue_tags": [
            "command_goal",
            "ui_ux",
            "layout",
            "xiaobian_learning",
            "round2",
            "template_system",
            "workflow_feedback",
            "priority_highest",
        ],
    },
    {
        "title": "小編第二輪深度學習：行銷與網站增強批次",
        "agent_label": "xiaobian.learning.ooschool.round2.marketing_web",
        "description": "針對行銷/網站相關課程，建立可直接落地的追蹤、導流與內容轉化方案。",
        "goals": "輸出導流漏斗、追蹤指標字典、內容轉化節點與 EDM 節奏表。",
        "constraints": "每一項都要有 KPI 與驗收方式。",
        "issue_tags": [
            "content",
            "research",
            "edm",
            "marketing_growth",
            "web_analytics",
            "conversion",
            "round2",
            "priority_highest",
        ],
    },
    {
        "title": "小編第二輪深度學習：Live2D製作交付規範",
        "agent_label": "xiaobian.learning.ooschool.round2.live2d_delivery",
        "description": "以 Live2D 相關課程為主，建立跨角色的可交接製作規範。",
        "goals": "輸出檔案命名規範、拆件清單、建模前檢查、交接包格式。",
        "constraints": "需能讓工程師/製作端直接接手執行。",
        "issue_tags": [
            "meeting_action",
            "live2d",
            "psd_cut",
            "handoff",
            "round2",
            "priority_highest",
        ],
    },
]


JXA_SCRIPT = r"""
ObjC.import('stdlib');
const Chrome = Application('Google Chrome');
if (!Chrome.running()) {
  console.log(JSON.stringify({ ok: false, error: 'chrome_not_running' }));
  $.exit(0);
}

const wins = Chrome.windows();
let tab = null;
for (let i = 0; i < wins.length; i++) {
  const t = wins[i].activeTab();
  if (!t) continue;
  const u = String(t.url() || '');
  if (u.includes('ooschool.cc/program-packages') && u.includes('/contents')) {
    tab = t;
    break;
  }
}
if (!tab && wins.length > 0) tab = wins[0].activeTab();
if (!tab) {
  console.log(JSON.stringify({ ok: false, error: 'no_active_tab' }));
  $.exit(0);
}

const url = String(tab.url() || '');
const title = String(tab.title() || '');
let bodyText = '';
try {
  bodyText = String(tab.execute({ javascript: 'document.body ? document.body.innerText : ""' }) || '');
} catch (e) {
  console.log(JSON.stringify({
    ok: false,
    error: 'execute_failed',
    url,
    detail: String(e),
  }));
  $.exit(0);
}

console.log(JSON.stringify({
  ok: true,
  url,
  title,
  body_text: bodyText,
}));
"""


@dataclass
class CourseProgress:
    name: str
    progress: int


def run_osascript(timeout_seconds: int) -> dict[str, Any]:
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", JXA_SCRIPT],
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    output = (proc.stdout or "").strip()
    if not output:
        output = (proc.stderr or "").strip()
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(
            f"osascript failed (code={proc.returncode}): {stderr or output}"
        )
    if not output:
        raise RuntimeError("osascript returned empty output")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid osascript JSON output: {output[:180]}") from exc
    return payload


def write_latest_snapshot_alias(markdown_text: str) -> Path:
    alias_path = (
        BASE_DIR / "data" / "knowledge_hub" / "notes" / "ooschool-page-live-snapshot.md"
    )
    alias_path.parent.mkdir(parents=True, exist_ok=True)
    alias_path.write_text(markdown_text, encoding="utf-8")
    return alias_path


def parse_courses(body_text: str) -> list[CourseProgress]:
    lines = [line.strip() for line in body_text.splitlines()]
    lines = [line for line in lines if line]

    parsed: list[CourseProgress] = []
    for idx in range(1, len(lines)):
        current = lines[idx]
        prev = lines[idx - 1]
        if not current.endswith("%"):
            continue
        pct_text = current[:-1].strip()
        if not pct_text.isdigit():
            continue
        progress = int(pct_text)
        if progress < 0 or progress > 100:
            continue
        if prev.endswith("%"):
            continue
        parsed.append(CourseProgress(name=prev, progress=progress))

    deduped: list[CourseProgress] = []
    seen: set[str] = set()
    for item in parsed:
        key = item.name.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def ensure_note_dir(now: datetime) -> Path:
    note_dir = BASE_DIR / "data" / "knowledge_hub" / "notes" / now.strftime("%Y%m%d")
    note_dir.mkdir(parents=True, exist_ok=True)
    return note_dir


def parse_snapshot_progress_map(markdown_text: str) -> dict[str, int]:
    progress_map: dict[str, int] = {}
    for line in str(markdown_text or "").splitlines():
        match = re.match(r"^\s*-\s*(.+?)\s*—\s*(\d{1,3})%\s*$", line.strip())
        if not match:
            continue
        course_name = str(match.group(1) or "").strip()
        progress = int(match.group(2) or 0)
        if not course_name:
            continue
        progress_map[course_name] = max(0, min(progress, 100))
    return progress_map


def load_previous_progress_map(snapshot_path: Path) -> dict[str, int]:
    # Prefer the current date snapshot (if already present), otherwise fall back to the latest dated snapshot.
    candidates: list[Path] = []
    if snapshot_path.exists():
        candidates.append(snapshot_path)
    notes_root = BASE_DIR / "data" / "knowledge_hub" / "notes"
    if notes_root.exists():
        dated_candidates = sorted(
            notes_root.glob("*/ooschool-page-live-snapshot.md"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        candidates.extend([p for p in dated_candidates if p not in candidates])

    for candidate in candidates:
        try:
            content = candidate.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        parsed = parse_snapshot_progress_map(content)
        if parsed:
            return parsed
    return {}


def build_snapshot_markdown(
    source_url: str,
    courses: list[CourseProgress],
    now: datetime,
    previous_progress_map: dict[str, int] | None = None,
) -> str:
    non_zero = sum(1 for item in courses if item.progress > 0)
    avg_progress = (
        (sum(item.progress for item in courses) / len(courses)) if courses else 0.0
    )
    prev_map = previous_progress_map or {}

    progress_changes: list[tuple[str, int, int, int]] = []
    for item in courses:
        prev = prev_map.get(item.name)
        if prev is None or int(prev) == int(item.progress):
            continue
        after = int(item.progress)
        before = int(prev)
        progress_changes.append((item.name, before, after, after - before))

    lines: list[str] = [
        "# OOSchool 課程頁即時快照",
        "",
        f"- 來源 URL: `{source_url}`",
        f"- 抓取時間: `{now.isoformat(timespec='seconds')}`",
        "- 抓取方式: Chrome AppleScript JavaScript（已登入頁面）",
        f"- 課程總數: `{len(courses)}`",
        f"- 非 0% 課程數: `{non_zero}`",
        f"- 平均進度: `{avg_progress:.2f}%`",
        f"- 與前次相比變動課程數: `{len(progress_changes)}`",
        "",
    ]

    lines.extend(
        [
            "## 本次進度變動",
            "",
        ]
    )
    if progress_changes:
        for name, before, after, delta in progress_changes:
            lines.append(f"- {name}: {before}% → {after}% ({delta:+d}%)")
    else:
        lines.append("- 無變動")

    lines.extend(
        [
            "",
            "## 課程與進度",
            "",
        ]
    )
    for item in courses:
        lines.append(f"- {item.name} — {item.progress}%")
    lines.append("")
    return "\n".join(lines)


def http_json(
    method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 20
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {text[:240]}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error {url}: {exc}") from exc


def fetch_existing_xiaobian_tasks(server_url: str) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "assigned_agent": "xiaobian",
            "status": "all",
            "limit": 200,
        }
    )
    url = f"{server_url.rstrip('/')}/agent/tasks?{query}"
    payload = http_json("GET", url)
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def queue_round2_tasks(server_url: str) -> dict[str, list[dict[str, Any]]]:
    existing = fetch_existing_xiaobian_tasks(server_url)
    existing_by_title = {
        str(item.get("title") or "").strip(): item
        for item in existing
        if str(item.get("title") or "").strip()
    }

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for template in ROUND2_TASK_TEMPLATES:
        title = template["title"]
        if title in existing_by_title:
            row = existing_by_title[title]
            skipped.append(
                {
                    "title": title,
                    "task_id": row.get("task_id"),
                    "status": row.get("status"),
                    "reason": "already_exists",
                }
            )
            continue

        payload = {
            "title": title,
            "description": template["description"],
            "assigned_agent": "xiaobian",
            "run_async": True,
            "goals": template["goals"],
            "constraints": template["constraints"],
            "issue_tags": template["issue_tags"],
            "agent_label": template["agent_label"],
            "output_format": "markdown_summary",
            "model_hint": "auto",
            "priority": "highest",
            "status": "queued",
        }
        url = f"{server_url.rstrip('/')}/agent/task"
        result = http_json("POST", url, payload=payload)
        task = result.get("task", {}) if isinstance(result, dict) else {}
        created.append(
            {
                "title": title,
                "task_id": task.get("task_id"),
                "status": task.get("status"),
            }
        )

    return {"created": created, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description="OOSchool logged-in page live sync")
    parser.add_argument(
        "--server-url", default=DEFAULT_SERVER_URL, help="Agent server base URL"
    )
    parser.add_argument(
        "--timeout", type=int, default=20, help="osascript timeout seconds"
    )
    parser.add_argument(
        "--enqueue-round2",
        action="store_true",
        help="Ensure round2 xiaobian tasks exist",
    )
    parser.add_argument(
        "--print-json", action="store_true", help="Print machine-readable JSON summary"
    )
    parser.add_argument(
        "--loop-interval",
        type=int,
        default=0,
        help="Run continuously every N seconds (0=run once)",
    )
    args = parser.parse_args()

    loop_interval = max(0, int(args.loop_interval))

    def run_once() -> dict[str, Any]:
        now = datetime.now()
        jxa = run_osascript(timeout_seconds=max(5, args.timeout))
        if not jxa.get("ok"):
            raise RuntimeError(
                f"Unable to read page: error={jxa.get('error')} detail={jxa.get('detail', '')}".strip()
            )

        source_url = str(jxa.get("url") or "")
        courses = parse_courses(str(jxa.get("body_text") or ""))
        if not courses:
            raise RuntimeError(
                "No course progress pairs parsed. Confirm the active tab is the course contents page."
            )

        note_dir = ensure_note_dir(now)
        snapshot_path = note_dir / "ooschool-page-live-snapshot.md"
        previous_progress_map = load_previous_progress_map(snapshot_path)
        snapshot_markdown = build_snapshot_markdown(
            source_url=source_url,
            courses=courses,
            now=now,
            previous_progress_map=previous_progress_map,
        )
        snapshot_path.write_text(snapshot_markdown, encoding="utf-8")
        alias_path = write_latest_snapshot_alias(snapshot_markdown)

        queue_result = {"created": [], "skipped": []}
        if args.enqueue_round2:
            queue_result = queue_round2_tasks(args.server_url)

        return {
            "ok": True,
            "captured_at": now.isoformat(timespec="seconds"),
            "source_url": source_url,
            "course_count": len(courses),
            "snapshot_path": str(snapshot_path),
            "latest_snapshot_alias": str(alias_path),
            "round2_queue": queue_result,
        }

    if loop_interval <= 0:
        summary = run_once()
        if args.print_json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("✅ OOSchool 即時同步完成")
            print(f"   source: {summary['source_url']}")
            print(f"   courses: {summary['course_count']}")
            print(f"   snapshot: {summary['snapshot_path']}")
            print(f"   latest: {summary['latest_snapshot_alias']}")
            if args.enqueue_round2:
                q = summary.get("round2_queue", {})
                print(
                    "   round2 tasks: "
                    f"created={len(q.get('created', []))}, skipped={len(q.get('skipped', []))}"
                )
        return 0

    print(
        f"🔄 OOSchool 連續同步模式已啟動，每 {loop_interval}s 重新抓取一次。按 Ctrl+C 結束。"
    )
    while True:
        try:
            summary = run_once()
            print(
                "[ooschool-sync] "
                f"{summary['captured_at']} "
                f"courses={summary['course_count']} "
                f"snapshot={summary['snapshot_path']}"
            )
        except KeyboardInterrupt:
            print("已停止連續同步。")
            return 0
        except Exception as exc:
            print(f"[ooschool-sync] error: {exc}")
        time.sleep(loop_interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

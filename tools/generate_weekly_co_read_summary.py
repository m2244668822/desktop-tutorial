#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共讀模式每週摘要產生器"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parents[1]
LOG_JSONL = BASE_DIR / "logs" / "co_reading_interactions.jsonl"
CONV_LOG_DIR = BASE_DIR / "data" / "conversation_logs"
REPORTS_DIR = BASE_DIR / "reports"


def _parse_iso_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _load_notes_from_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    notes: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                notes.append(obj)
        except Exception:
            continue
    return notes


def _load_notes_from_conversation_logs(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    notes: List[Dict[str, Any]] = []
    for file_path in sorted(path.glob("*_session_*.json")):
        try:
            obj = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(obj, dict):
            continue

        co_notes = obj.get("co_read_notes", [])
        if isinstance(co_notes, list):
            for note in co_notes:
                if isinstance(note, dict):
                    notes.append(note)

    return notes


def _deduplicate_notes(notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []

    for note in notes:
        ts = str(note.get("timestamp", ""))
        focus = str(note.get("question_focus", ""))
        tip = str(note.get("interaction_tip", ""))
        key = (ts, focus, tip)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(note)

    return deduped


def _filter_recent_notes(
    notes: List[Dict[str, Any]], days: int
) -> List[Dict[str, Any]]:
    cutoff = datetime.now() - timedelta(days=days)
    filtered: List[Dict[str, Any]] = []

    for note in notes:
        ts = _parse_iso_datetime(str(note.get("timestamp", "")))
        if ts is None:
            continue
        if ts >= cutoff:
            filtered.append(note)

    return filtered


def _build_stats(notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    focus_counter: Counter[str] = Counter()
    tip_counter: Counter[str] = Counter()
    daily_counter: defaultdict[str, int] = defaultdict(int)
    prompt_suggestions: List[str] = []

    for note in notes:
        focus = str(note.get("question_focus", "")).strip()
        if focus:
            focus_counter[focus] += 1

        tip = str(note.get("interaction_tip", "")).strip()
        if tip:
            tip_counter[tip] += 1

        ts = _parse_iso_datetime(str(note.get("timestamp", "")))
        if ts:
            daily_counter[ts.strftime("%Y-%m-%d")] += 1

        next_prompt = str(note.get("next_prompt_suggestion", "")).strip()
        if next_prompt:
            prompt_suggestions.append(next_prompt)

    top_focus = focus_counter.most_common(10)
    top_tips = tip_counter.most_common(5)
    top_prompts = Counter(prompt_suggestions).most_common(10)

    return {
        "total_notes": len(notes),
        "top_focus": top_focus,
        "top_tips": top_tips,
        "daily_counts": dict(sorted(daily_counter.items())),
        "top_prompts": top_prompts,
    }


def _render_markdown(stats: Dict[str, Any], days: int) -> str:
    now = datetime.now()

    lines = [
        f"# 共讀模式每週摘要（最近 {days} 天）",
        "",
        f"**生成時間**: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## 📊 摘要",
        "",
        "| 指標 | 數值 |",
        "|------|------|",
        f"| 共讀筆記總數 | {stats['total_notes']} |",
        "",
        "---",
        "",
        "## 🎯 最高頻學習焦點",
        "",
    ]

    if stats["top_focus"]:
        lines.append("| 焦點 | 次數 |")
        lines.append("|------|------|")
        for focus, count in stats["top_focus"]:
            lines.append(f"| {focus} | {count} |")
    else:
        lines.append("*本週尚無共讀筆記*")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 🧠 互動策略分佈",
            "",
        ]
    )

    if stats["top_tips"]:
        lines.append("| 互動策略 | 次數 |")
        lines.append("|----------|------|")
        for tip, count in stats["top_tips"]:
            lines.append(f"| {tip} | {count} |")
    else:
        lines.append("*本週尚無互動策略資料*")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 📅 每日共讀筆記數",
            "",
        ]
    )

    if stats["daily_counts"]:
        lines.append("| 日期 | 筆數 |")
        lines.append("|------|------|")
        for date, count in stats["daily_counts"].items():
            lines.append(f"| {date} | {count} |")
    else:
        lines.append("*本週尚無每日資料*")

    lines.extend(
        [
            "",
            "---",
            "",
            "## ✍️ 下輪建議提問（Top 10）",
            "",
        ]
    )

    if stats["top_prompts"]:
        for idx, (prompt, count) in enumerate(stats["top_prompts"], 1):
            lines.append(f"{idx}. {prompt}（{count} 次）")
    else:
        lines.append("*本週尚無建議提問資料*")

    lines.extend(
        [
            "",
            "---",
            "",
            "## ✅ 下週建議",
            "",
            "1. 每次學習提問後多補一句『幫我出一題檢核題』，提升回合學習密度。",
            "2. 每日固定 1 次複習提問（24h 複習法），讓共讀筆記可形成週期記憶。",
            "3. 每週至少選 3 個高頻焦點，做一次整合性總結。",
            "",
            f"*報告生成時間: {now.isoformat()}*",
        ]
    )

    return "\n".join(lines)


def generate_weekly_summary(days: int = 7) -> Dict[str, Any]:
    notes_from_jsonl = _load_notes_from_jsonl(LOG_JSONL)
    notes_from_sessions = _load_notes_from_conversation_logs(CONV_LOG_DIR)

    all_notes = _deduplicate_notes(notes_from_jsonl + notes_from_sessions)
    recent_notes = _filter_recent_notes(all_notes, days=days)
    stats = _build_stats(recent_notes)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    md_path = REPORTS_DIR / f"co_read_summary_d{days}_{date_tag}.md"
    json_path = REPORTS_DIR / f"co_read_summary_d{days}_{date_tag}.json"

    md_path.write_text(_render_markdown(stats, days=days), encoding="utf-8")

    payload = {
        "generated_at": datetime.now().isoformat(),
        "days": days,
        "sources": {
            "jsonl_exists": LOG_JSONL.exists(),
            "conversation_logs_exists": CONV_LOG_DIR.exists(),
        },
        "stats": stats,
        "report_markdown": str(md_path),
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "days": days,
        "total_notes": stats["total_notes"],
        "markdown": str(md_path),
        "json": str(json_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成共讀模式每週摘要")
    parser.add_argument("--days", type=int, default=7, help="統計天數，預設 7")
    args = parser.parse_args()

    result = generate_weekly_summary(days=args.days)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

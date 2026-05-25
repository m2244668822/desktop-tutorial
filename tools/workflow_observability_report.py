#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build an observability summary from workflow runtime logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "reports" / "observability"


def parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def load_runs(
    runs_dirs: list[Path], since: datetime | None = None, limit: int = 300
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    files: list[Path] = []
    for runs_dir in runs_dirs:
        if not runs_dir.exists():
            continue
        files.extend(runs_dir.glob("wf-*.json"))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[: limit * 2]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        created_at = parse_iso(payload.get("created_at", ""))
        if since and created_at and created_at < since:
            continue
        payload["_path"] = str(path)
        rows.append(payload)
        if len(rows) >= limit:
            break
    return rows


def build_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(runs)
    if total == 0:
        return {
            "total_runs": 0,
            "success_rate": 0.0,
            "partial_rate": 0.0,
            "failed_rate": 0.0,
            "avg_duration_ms": 0.0,
            "avg_retries_used": 0.0,
            "error_breakdown": {},
            "top_failed_tools": {},
            "retry_hotspots": {},
            "latest_failed_runs": [],
        }

    status_counter: Counter[str] = Counter()
    error_counter: Counter[str] = Counter()
    failed_tool_counter: Counter[str] = Counter()
    retry_counter: Counter[str] = Counter()
    durations: list[int] = []
    retries: list[int] = []
    failed_runs: list[dict[str, Any]] = []

    for row in runs:
        state = row.get("task_state", {})
        status = str(state.get("overall_status", "failed") or "failed").lower()
        status_counter[status] += 1
        durations.append(int(state.get("duration_ms", 0) or 0))
        retries.append(int(state.get("retries_used", 0) or 0))

        observability = (
            state.get("observability", {})
            if isinstance(state.get("observability"), dict)
            else {}
        )
        for key, count in (observability.get("error_breakdown", {}) or {}).items():
            error_counter[str(key)] += int(count or 0)

        steps = state.get("steps", []) if isinstance(state.get("steps"), list) else []
        for step in steps:
            tool = str(step.get("tool_name", ""))
            step_status = str(step.get("status", ""))
            attempts = int(step.get("attempts", 0) or 0)
            if attempts > 1 and tool:
                retry_counter[tool] += 1
            if step_status == "failed" and tool:
                failed_tool_counter[tool] += 1
            if step.get("error_class"):
                error_counter[str(step.get("error_class"))] += 1

        if status == "failed":
            failed_runs.append(
                {
                    "task_id": state.get("task_id", ""),
                    "trace_id": state.get("trace_id", ""),
                    "created_at": row.get("created_at", ""),
                    "log_path": state.get("log_path", row.get("_path", "")),
                    "failed_steps": int(state.get("failed_steps", 0) or 0),
                }
            )

    return {
        "total_runs": total,
        "success_rate": round(status_counter.get("success", 0) / total, 4),
        "partial_rate": round(status_counter.get("partial", 0) / total, 4),
        "failed_rate": round(status_counter.get("failed", 0) / total, 4),
        "avg_duration_ms": round(sum(durations) / total, 2),
        "avg_retries_used": round(sum(retries) / total, 2),
        "error_breakdown": dict(error_counter.most_common(12)),
        "top_failed_tools": dict(failed_tool_counter.most_common(10)),
        "retry_hotspots": dict(retry_counter.most_common(10)),
        "latest_failed_runs": failed_runs[:10],
    }


def build_markdown(summary: dict[str, Any], since_label: str) -> str:
    lines = [
        "# Workflow Observability Report",
        "",
        f"- Generated at: {datetime.now().isoformat()}",
        f"- Window: {since_label}",
        f"- Total runs: {summary.get('total_runs', 0)}",
        "",
        "## Core KPIs",
        f"- Success rate: {summary.get('success_rate', 0.0):.2%}",
        f"- Partial rate: {summary.get('partial_rate', 0.0):.2%}",
        f"- Failed rate: {summary.get('failed_rate', 0.0):.2%}",
        f"- Avg duration (ms): {summary.get('avg_duration_ms', 0.0)}",
        f"- Avg retries used: {summary.get('avg_retries_used', 0.0)}",
        "",
        "## Error Breakdown",
    ]

    error_breakdown = summary.get("error_breakdown", {}) or {}
    if error_breakdown:
        for key, value in error_breakdown.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Top Failed Tools")
    top_failed_tools = summary.get("top_failed_tools", {}) or {}
    if top_failed_tools:
        for key, value in top_failed_tools.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Retry Hotspots")
    retry_hotspots = summary.get("retry_hotspots", {}) or {}
    if retry_hotspots:
        for key, value in retry_hotspots.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Latest Failed Runs")
    latest_failed = summary.get("latest_failed_runs", []) or []
    if latest_failed:
        for item in latest_failed:
            lines.append(
                f"- task={item.get('task_id')} trace={item.get('trace_id')} failed_steps={item.get('failed_steps')} log={item.get('log_path')}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate workflow observability report"
    )
    parser.add_argument("--workspace", default=str(BASE_DIR), help="Workspace root")
    parser.add_argument("--days", type=int, default=7, help="Lookback days")
    parser.add_argument("--limit", type=int, default=300, help="Max run logs to load")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    since = datetime.now() - timedelta(days=max(0, int(args.days or 0)))
    runs = load_runs(
        [workspace / "data" / "workflow_runs", workspace / "logs" / "workflow_runs"],
        since=since,
        limit=max(1, int(args.limit or 1)),
    )
    summary = build_summary(runs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"observability_{timestamp}.json"
    md_path = OUT_DIR / f"observability_{timestamp}.md"
    latest_json = OUT_DIR / "latest.json"
    latest_md = OUT_DIR / "latest.md"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(workspace),
        "window_days": int(args.days),
        "summary": summary,
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    md_text = build_markdown(summary, since_label=f"last {int(args.days)} day(s)")

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print("✅ Observability report generated")
    print(f"   runs_analyzed: {summary.get('total_runs', 0)}")
    print(f"   success_rate: {summary.get('success_rate', 0.0):.2%}")
    print(f"   failed_rate: {summary.get('failed_rate', 0.0):.2%}")
    print(f"   json: {json_path}")
    print(f"   markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

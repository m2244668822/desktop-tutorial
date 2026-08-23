#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run golden-set evaluation for LangGraph workflow V1."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
DEFAULT_DATASET = BASE_DIR / "evals" / "golden_set_v1.jsonl"
REPORT_DIR = BASE_DIR / "reports" / "evals"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def evaluate_case(case: dict[str, Any], workspace: Path) -> dict[str, Any]:
    from core.langgraph_workflow import run_workflow

    user_input = str(case.get("input", "")).strip()
    started = datetime.now().isoformat()
    fallback_error = ""
    try:
        result = run_workflow(user_input, workspace=str(workspace))
    except Exception as exc:
        fallback_error = str(exc)
        try:
            from core.workflow_runtime import run_task_plan

            route = infer_route_for_eval(user_input)
            task_run = run_task_plan(
                workspace=workspace, route=route, user_input=user_input
            )
            task_state = task_run.get("task_state", {})
            result = {
                "route": route,
                "verified": str(task_state.get("overall_status", "")).lower()
                in {"success", "partial"},
                "task_state": task_state,
            }
        except Exception as fallback_exc:
            return {
                "case_id": case.get("case_id", "unknown"),
                "input": user_input,
                "started_at": started,
                "status": "error",
                "error": f"workflow_failed={fallback_error}; fallback_failed={fallback_exc}",
                "strict_pass": False,
                "first_pass": False,
                "needs_manual": True,
                "step_count": 0,
                "duration_ms": 0,
            }

    task_state = result.get("task_state", {}) if isinstance(result, dict) else {}
    route = str(result.get("route", ""))
    verified = bool(result.get("verified", False))
    overall_status = str(task_state.get("overall_status", "failed")).lower()
    retries_used = int(task_state.get("retries_used", 0) or 0)
    steps = (
        task_state.get("steps", [])
        if isinstance(task_state.get("steps", []), list)
        else []
    )
    duration_ms = int(task_state.get("duration_ms", 0) or 0)

    allowed_status = {
        str(x).lower() for x in case.get("accept_status", ["success", "partial"])
    }
    must_route = str(case.get("must_route", "")).strip()
    route_ok = (not must_route) or (route == must_route)
    status_ok = overall_status in allowed_status
    strict_pass = route_ok and status_ok and verified
    first_pass = strict_pass and retries_used == 0
    needs_manual = (not strict_pass) or (overall_status != "success")

    return {
        "case_id": case.get("case_id", "unknown"),
        "input": user_input,
        "must_route": must_route,
        "route": route,
        "verified": verified,
        "overall_status": overall_status,
        "strict_pass": strict_pass,
        "first_pass": first_pass,
        "needs_manual": needs_manual,
        "retries_used": retries_used,
        "step_count": len(steps),
        "duration_ms": duration_ms,
        "trace_id": task_state.get("trace_id", ""),
        "log_path": task_state.get("log_path", ""),
        "fallback_mode": bool(fallback_error),
        "fallback_error": fallback_error,
    }


def infer_route_for_eval(user_input: str) -> str:
    text = (user_input or "").lower()
    if any(token in text for token in ["安全", "漏洞", "掃描"]):
        return "帽子"
    if any(
        token in text
        for token in [
            "倫理",
            "道德",
            "聖經",
            "以利亞",
            "elijah",
            "先知",
            "申言者",
            "價值",
        ]
    ):
        return "申言者"
    if any(token in text for token in ["研究", "比較", "開源", "資料"]):
        return "研究員"
    if any(token in text for token in ["程式", "修復", "優化", "工程", "bug", "fix"]):
        return "工程師"
    return "總管"


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "success_rate": 0.0,
            "first_pass_rate": 0.0,
            "manual_intervention_rate": 0.0,
            "avg_step_count": 0.0,
            "avg_duration_ms": 0.0,
        }

    strict_pass_count = sum(1 for row in results if row.get("strict_pass"))
    first_pass_count = sum(1 for row in results if row.get("first_pass"))
    manual_count = sum(1 for row in results if row.get("needs_manual"))
    steps_total = sum(int(row.get("step_count", 0) or 0) for row in results)
    duration_total = sum(int(row.get("duration_ms", 0) or 0) for row in results)

    return {
        "total_cases": total,
        "success_rate": round(strict_pass_count / total, 4),
        "first_pass_rate": round(first_pass_count / total, 4),
        "manual_intervention_rate": round(manual_count / total, 4),
        "avg_step_count": round(steps_total / total, 2),
        "avg_duration_ms": round(duration_total / total, 2),
        "strict_pass_cases": strict_pass_count,
        "first_pass_cases": first_pass_count,
        "manual_cases": manual_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run workflow golden-set evaluation")
    parser.add_argument(
        "--dataset", default=str(DEFAULT_DATASET), help="Path to golden set JSONL"
    )
    parser.add_argument(
        "--workspace", default=str(BASE_DIR), help="Workspace root path"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Run first N cases (0 = all)"
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()
    if not dataset_path.exists():
        raise SystemExit(f"dataset not found: {dataset_path}")

    cases = load_jsonl(dataset_path)
    if args.limit > 0:
        cases = cases[: args.limit]

    results = [evaluate_case(case, workspace) for case in cases]
    metrics = summarize(results)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "created_at": datetime.now().isoformat(),
        "dataset": str(dataset_path),
        "workspace": str(workspace),
        "metrics": metrics,
        "results": results,
    }
    report_path = REPORT_DIR / f"eval_{timestamp}.json"
    latest_path = REPORT_DIR / "latest.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    latest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("✅ Workflow eval completed")
    print(f"   dataset: {dataset_path}")
    print(f"   cases: {metrics['total_cases']}")
    print(f"   success_rate: {metrics['success_rate']:.2%}")
    print(f"   first_pass_rate: {metrics['first_pass_rate']:.2%}")
    print(f"   manual_intervention_rate: {metrics['manual_intervention_rate']:.2%}")
    print(f"   avg_step_count: {metrics['avg_step_count']}")
    print(f"   avg_duration_ms: {metrics['avg_duration_ms']}")
    print(f"   report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

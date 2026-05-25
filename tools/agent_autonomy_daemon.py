#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent autonomy daemon

Goals:
1) Continuously execute queued tasks without manual prompt each time.
2) Run skill stability/conflict checks on a schedule.
3) Keep a lightweight backend permission snapshot.
4) Persist runtime state for frontend/ops visibility.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.workflow_runtime import run_task_plan


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


DATA_ROOT = _resolve_data_root(BASE_DIR)
AUTONOMY_DIR = DATA_ROOT / "autonomy"
QUEUE_FILE = AUTONOMY_DIR / "task_queue.json"
STATE_FILE = AUTONOMY_DIR / "daemon_state.json"
REPORT_FILE = AUTONOMY_DIR / "skill_stability_report.json"
LOCK_FILE = AUTONOMY_DIR / "busy.lock"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dirs() -> None:
    AUTONOMY_DIR.mkdir(parents=True, exist_ok=True)


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


def git_summary() -> str:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        lines = [line.rstrip() for line in out.splitlines() if line.strip()]
        if proc.returncode == 0:
            return "\n".join(lines[:12]) if lines else "clean"
        merged = "\n".join([part for part in (out, err) if part]).lower()
        if any(
            marker in merged
            for marker in (
                "invalid sha1 pointer",
                "object file",
                "object corrupt",
                "missing blob",
                "invalid reflog entry",
                "fatal: bad object",
            )
        ):
            return "degraded: git metadata corrupt"
        if "not a git repository" in merged:
            return "degraded: not a git repository"
        return f"degraded: git status unavailable (rc={proc.returncode})"
    except Exception:
        return "degraded: git command unavailable"


def env_permission_status() -> dict[str, Any]:
    token = (os.environ.get("SERVER_API_TOKEN") or "").strip()
    required = (os.environ.get("SERVER_API_TOKEN_REQUIRED") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return {
        "server_api_token_required": required,
        "server_api_token_configured": bool(token),
        "checked_at": now_iso(),
    }


def load_skill_map(base: Path) -> dict[str, dict[str, str]]:
    skill_map: dict[str, dict[str, str]] = {}
    if not base.exists():
        return skill_map
    for skill_md in base.glob("*/SKILL.md"):
        folder_name = skill_md.parent.name
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            text = ""
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        skill_map[folder_name] = {
            "path": str(skill_md),
            "signature": first_line,
        }
    return skill_map


def check_skill_stability() -> dict[str, Any]:
    local_skills = load_skill_map(BASE_DIR / "skills")
    gemini_skills = load_skill_map(BASE_DIR / ".gemini" / "skills")

    local_names = set(local_skills.keys())
    gemini_names = set(gemini_skills.keys())
    both = sorted(local_names & gemini_names)

    conflicts: list[dict[str, str]] = []
    for name in both:
        local_sig = local_skills[name].get("signature", "")
        gemini_sig = gemini_skills[name].get("signature", "")
        if local_sig != gemini_sig:
            conflicts.append(
                {
                    "skill": name,
                    "local_path": local_skills[name]["path"],
                    "gemini_path": gemini_skills[name]["path"],
                    "local_signature": local_sig,
                    "gemini_signature": gemini_sig,
                }
            )

    report = {
        "checked_at": now_iso(),
        "local_skill_count": len(local_skills),
        "gemini_skill_count": len(gemini_skills),
        "shared_skill_count": len(both),
        "shared_skills": both,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "stable": len(conflicts) == 0,
    }
    write_json(REPORT_FILE, report)
    return report


def load_queue() -> list[dict[str, Any]]:
    data = read_json(QUEUE_FILE, {"tasks": []})
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        return []
    return tasks


def save_queue(tasks: list[dict[str, Any]]) -> None:
    write_json(QUEUE_FILE, {"updated_at": now_iso(), "tasks": tasks})


def can_execute() -> bool:
    if LOCK_FILE.exists():
        return False
    return True


def pick_pending_task(tasks: list[dict[str, Any]]) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    for idx, task in enumerate(tasks):
        if str(task.get("status", "pending")).lower() == "pending":
            return idx, task
    return None, None


def normalize_task(task: dict[str, Any]) -> tuple[str, str]:
    route = str(task.get("route", "總管") or "總管")
    user_input = str(task.get("input", "")).strip()
    return route, user_input


def execute_one_task(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    idx, task = pick_pending_task(tasks)
    if task is None:
        return {"executed": False, "reason": "no_pending_task"}

    route, user_input = normalize_task(task)
    if not user_input:
        tasks[idx]["status"] = "failed"
        tasks[idx]["error"] = "empty_input"
        tasks[idx]["updated_at"] = now_iso()
        save_queue(tasks)
        return {"executed": False, "reason": "empty_input"}

    LOCK_FILE.write_text(now_iso(), encoding="utf-8")
    tasks[idx]["status"] = "running"
    tasks[idx]["updated_at"] = now_iso()
    save_queue(tasks)

    try:
        result = run_task_plan(BASE_DIR, route, user_input)
        task_state = result.get("task_state", {}) if isinstance(result, dict) else {}
        ok = str(task_state.get("overall_status", "")).lower() == "success"

        tasks[idx]["status"] = "done" if ok else "failed"
        tasks[idx]["route"] = route
        tasks[idx]["task_id"] = task_state.get("task_id", "")
        tasks[idx]["trace_id"] = task_state.get("trace_id", "")
        tasks[idx]["log_path"] = task_state.get("log_path", "")
        tasks[idx]["updated_at"] = now_iso()
        tasks[idx]["result_summary"] = {
            "overall_status": task_state.get("overall_status", "unknown"),
            "completed_steps": task_state.get("completed_steps", 0),
            "failed_steps": task_state.get("failed_steps", 0),
        }
        save_queue(tasks)
        return {"executed": True, "success": ok, "task_id": task_state.get("task_id", "")}
    except Exception as exc:
        tasks[idx]["status"] = "failed"
        tasks[idx]["updated_at"] = now_iso()
        tasks[idx]["error"] = str(exc)
        save_queue(tasks)
        return {"executed": True, "success": False, "error": str(exc)}
    finally:
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def write_state(payload: dict[str, Any]) -> None:
    base = read_json(STATE_FILE, {})
    base.update(payload)
    base["updated_at"] = now_iso()
    write_json(STATE_FILE, base)


def run_daemon(interval_seconds: int, skill_check_minutes: int) -> None:
    ensure_dirs()
    if not QUEUE_FILE.exists():
        save_queue([])

    next_skill_check = datetime.now()
    print(f"[autonomy] started at {now_iso()} interval={interval_seconds}s")

    while True:
        cycle_started = time.time()
        permission = env_permission_status()

        if datetime.now() >= next_skill_check:
            skill_report = check_skill_stability()
            next_skill_check = datetime.now() + timedelta(minutes=skill_check_minutes)
        else:
            skill_report = read_json(REPORT_FILE, {"stable": True, "conflict_count": 0})

        tasks = load_queue()
        pending_count = sum(1 for t in tasks if str(t.get("status", "pending")).lower() == "pending")

        execution_result = {"executed": False, "reason": "busy_or_no_task"}
        if can_execute():
            execution_result = execute_one_task(tasks)

        write_state(
            {
                "daemon_status": "running",
                "cycle_started_at": now_iso(),
                "pending_tasks": pending_count,
                "skill_stable": bool(skill_report.get("stable", False)),
                "skill_conflicts": int(skill_report.get("conflict_count", 0) or 0),
                "permission": permission,
                "git_summary": git_summary(),
                "last_execution": execution_result,
            }
        )

        elapsed = time.time() - cycle_started
        sleep_for = max(1.0, float(interval_seconds) - elapsed)
        time.sleep(sleep_for)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent autonomy daemon")
    parser.add_argument("--interval", type=int, default=30, help="Daemon cycle interval in seconds")
    parser.add_argument(
        "--skill-check-minutes",
        type=int,
        default=10,
        help="Skill stability check frequency in minutes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_daemon(interval_seconds=max(5, args.interval), skill_check_minutes=max(1, args.skill_check_minutes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


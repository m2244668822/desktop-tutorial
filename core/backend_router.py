#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backend routing policy used by desktop/app layers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping
try:
    from core.llm_cns import classify_purpose
except Exception:
    classify_purpose = None

EXECUTION_KEYWORDS = (
    "建立",
    "執行",
    "修復",
    "整理",
    "報告",
    "導入",
    "知識庫",
    "索引",
    "save",
    "write",
    "build",
    "ingest",
    "fix",
    "repair",
    "workflow",
)
BASE_DIR = Path(__file__).resolve().parent.parent
_DEBUG_LOG_PATH = BASE_DIR / ".cursor" / "debug-baa814.log"


def _agent_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    payload = {
        "sessionId": "baa814",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion


def infer_backend_purpose(
    user_message: str, workflow: Mapping[str, Any] | None = None
) -> str:
    """Classify request as execution or discussion for backend policy."""
    text = (user_message or "").lower()
    run_id = ""
    task_state = {}
    if isinstance(workflow, Mapping):
        task_state = workflow.get("task_state", {}) or {}
        run_id = str(workflow.get("run_id", "") or "")
    run_id = run_id or "run-unknown"

    if classify_purpose is not None:
        overall_status = ""
        completed_steps = 0
        if isinstance(task_state, Mapping):
            completed_steps = int(task_state.get("completed_steps", 0) or 0)
            overall_status = str(task_state.get("overall_status", "") or "")
        purpose = classify_purpose(
            user_message=user_message,
            completed_steps=completed_steps,
            overall_status=overall_status,
        )
        _agent_log(
            run_id,
            "H2",
            "core/backend_router.py:infer_backend_purpose",
            "classified by llm_cns",
            {"purpose": purpose, "message_preview": text[:120]},
        )
        return purpose

    if any(token in text for token in EXECUTION_KEYWORDS):
        _agent_log(
            run_id,
            "H2",
            "core/backend_router.py:infer_backend_purpose",
            "classified by keyword",
            {"message_preview": text[:120], "reason": "execution_keyword"},
        )
        return "execution"

    if isinstance(task_state, Mapping):
        completed_steps = int(task_state.get("completed_steps", 0) or 0)
        overall_status = str(task_state.get("overall_status", "") or "").lower()
        if completed_steps > 0 or overall_status in {"success", "partial"}:
            _agent_log(
                run_id,
                "H2",
                "core/backend_router.py:infer_backend_purpose",
                "classified by task_state",
                {"completed_steps": completed_steps, "overall_status": overall_status},
            )
            return "execution"

    _agent_log(
        run_id,
        "H2",
        "core/backend_router.py:infer_backend_purpose",
        "classified as discussion",
        {"message_preview": text[:120], "completed_steps": task_state.get("completed_steps", 0)},
    )
    return "discussion"


def allow_open_source_for_purpose(purpose: str) -> bool:
    """Only allow open-source chat fallback for discussion-style turns."""
    return (purpose or "").strip().lower() == "discussion"

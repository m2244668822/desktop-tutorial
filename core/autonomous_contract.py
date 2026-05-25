#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autonomous ReAct contract guardrails and validation helpers."""

from __future__ import annotations

import json
from typing import Any


ALLOWED_TOOLS = {
    "query_database",
    "search_knowledge_base",
    "call_external_api",
    "send_notification_email",
}

HIGH_RISK_TOOLS = {
    "call_external_api",
    "send_notification_email",
}


def parse_agent_json(text: str) -> tuple[bool, dict[str, Any], str]:
    raw = str(text or "").strip()
    if not raw:
        return False, {}, "empty_output"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, {}, f"json_decode_error:{exc}"
    if not isinstance(payload, dict):
        return False, {}, "root_must_be_object"
    return True, payload, ""


def validate_react_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if "action" in payload:
        action = payload.get("action")
        if not isinstance(action, dict):
            return False, "action_must_be_object"
        name = str(action.get("name", "")).strip()
        if name not in ALLOWED_TOOLS:
            return False, f"tool_not_allowed:{name}"
        params = action.get("parameters")
        if not isinstance(params, dict):
            return False, "parameters_must_be_object"
        if not isinstance(payload.get("thought", ""), str):
            return False, "thought_required_for_action"
        return True, "ok"
    if "final_answer" in payload:
        if not isinstance(payload.get("final_answer"), str):
            return False, "final_answer_must_be_string"
        if not isinstance(payload.get("thought", ""), str):
            return False, "thought_required_for_final"
        return True, "ok"
    return False, "must_have_action_or_final_answer"


def requires_human_review(payload: dict[str, Any]) -> tuple[bool, str]:
    action = payload.get("action")
    if not isinstance(action, dict):
        return False, ""
    name = str(action.get("name", "")).strip()
    if name in HIGH_RISK_TOOLS:
        return True, f"human_review_required:{name}"
    return False, ""


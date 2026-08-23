#!/usr/bin/env python3
"""Append-only audit events for agent collaboration and repair learning."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.audit_chain import HashChainAuditLog
from core.content_sanitizer import ExternalContentSanitizer
from core.data_paths import resolve_data_root
from core.trevor_identity import TREVOR_AGENT_ID, TREVOR_DISPLAY_NAME, normalize_trevor_identity

AUDIT_RELATIVE_PATH = Path("logs") / "agent_collaboration_audit.jsonl"

TRAINING_RULES: dict[str, dict[str, Any]] = {
    "ENTRY_CHECK_ORDER": {
        "owner": "工程師",
        "description": "入口問題先測 5001，再測 5443，最後才查前端。",
        "training_tags": ["entry_stability", "gateway_health", "frontend_backend"],
    },
    "OPENCLAW_FALLBACK_REQUIRED": {
        "owner": "工程師",
        "description": "OpenClaw 只要沒有可讀回覆，就必須回退 DesktopBridge。",
        "training_tags": ["openclaw_fallback", "desktopbridge_recovery"],
    },
    "N8N_OPTIONAL_ONLY": {
        "owner": "總管中樞",
        "description": "n8n 是 optional，不能因為排程器沒開就讓前端對話失敗。",
        "training_tags": ["optional_scheduler", "n8n_degraded"],
    },
    "AUDIT_EVERY_REPAIR": {
        "owner": "總管中樞",
        "description": "每次智能體做錯選擇或補救，都要寫入審計事件，不可只留在 console。",
        "training_tags": ["audit_learning", "repair_traceability"],
    },
    "PYTHON_RUNTIME_RISK": {
        "owner": "工程師",
        "description": "Python 3.14 的 Pydantic v1 warning 要視為中期風險，主 runtime 優先固定在 3.11/3.12。",
        "training_tags": ["python_runtime", "pydantic_v1", "compatibility_risk"],
    },
}


def record_agent_collaboration_event(
    workspace: str | Path,
    *,
    task_goal: str,
    agent: str,
    route: str,
    decision: str,
    outcome: str,
    remedy: str = "",
    score_delta: int = 0,
    details: dict[str, Any] | None = None,
    rule_ids: list[str] | None = None,
    assigned_agents: list[str] | None = None,
    severity: str = "",
    learning_action: str = "",
    training_tags: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    next_guardrail: str = "",
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    path = root / AUDIT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    source_role = str(agent or TREVOR_DISPLAY_NAME).strip() or TREVOR_DISPLAY_NAME
    identity = normalize_trevor_identity(role=source_role)
    event = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat(),
        "task_goal": task_goal,
        "agent": TREVOR_DISPLAY_NAME,
        "identity": TREVOR_AGENT_ID,
        "source_role": source_role,
        "capability_mode": identity.capability_mode,
        "route": route,
        "decision": decision,
        "outcome": outcome,
        "remedy": remedy,
        "score_delta": int(score_delta),
        "details": details or {},
    }
    overlay = {
        "rule_ids": rule_ids,
        "assigned_agents": assigned_agents,
        "severity": severity,
        "learning_action": learning_action,
        "training_tags": training_tags,
        "evidence": evidence,
        "next_guardrail": next_guardrail,
    }
    for key, value in overlay.items():
        if value not in (None, "", [], {}):
            event[key] = value
    sanitizer = ExternalContentSanitizer()

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, str):
            return sanitizer.sanitize(message=value).payload["message"]
        return value

    event = redact(event)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    chain = HashChainAuditLog(resolve_data_root(root) / "audit" / "events.jsonl")
    chain_event = chain.append("agent_collaboration", event)
    event["chain_event_id"] = chain_event["event_id"]
    event["chain_hash"] = chain_event["event_hash"]
    return event


__all__ = ["AUDIT_RELATIVE_PATH", "TRAINING_RULES", "record_agent_collaboration_event"]

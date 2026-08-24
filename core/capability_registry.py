#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capability registry for the Perob super-platform.

The registry is the main system's role sheet: every heavy tool or sidecar
reports its purpose, readiness, cost class, and fallback without being imported
into the web runtime.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from core.trevor_identity import TREVOR_AGENT_ID, TREVOR_DISPLAY_NAME, normalize_trevor_identity


def _tcp_up(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _status_from_ready(ready: bool, *, disabled: bool = False, degraded: bool = False) -> str:
    if disabled:
        return "disabled"
    if ready:
        return "ready"
    if degraded:
        return "degraded"
    return "offline"


def _capability(
    *,
    capability_id: str,
    label: str,
    kind: str,
    ready: bool,
    status: str | None = None,
    required: bool = False,
    cost_class: str = "local",
    task_types: list[str] | None = None,
    risk_level: str = "low",
    owner_agent: str = TREVOR_AGENT_ID,
    fallback: str = "",
    endpoint: str = "",
    **extra: Any,
) -> dict[str, Any]:
    owner_identity = normalize_trevor_identity(agent=owner_agent, role=owner_agent)
    payload = {
        "id": capability_id,
        "label": label,
        "kind": kind,
        "ready": bool(ready),
        "status": status or _status_from_ready(bool(ready)),
        "required": bool(required),
        "cost_class": cost_class,
        "task_types": task_types or [],
        "risk_level": risk_level,
        "owner_agent": TREVOR_AGENT_ID,
        "owner_role": TREVOR_DISPLAY_NAME,
        "owner_capability_mode": owner_identity.capability_mode,
        "fallback": fallback,
        "endpoint": endpoint,
    }
    payload.update(extra)
    return payload


def _provider_rows(provider_status: dict[str, Any]) -> list[dict[str, Any]]:
    public_rows = provider_status.get("providers")
    if isinstance(public_rows, list):
        return [
            {
                key: item.get(key)
                for key in (
                    "provider",
                    "label",
                    "model",
                    "family",
                    "enabled",
                    "health",
                    "latency_ms",
                    "quota",
                    "circuit",
                    "disabled_reason",
                    "free_only",
                    "control_authority",
                )
                if key in item
            }
            for item in public_rows
            if isinstance(item, dict) and item.get("provider")
        ]
    legacy_rows = provider_status.get("provider_catalog")
    if not isinstance(legacy_rows, list):
        return []
    normalized = []
    for item in legacy_rows:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or item.get("key") or "").strip().lower()
        if not provider:
            continue
        tier = str((item.get("classification") or {}).get("tier") or "disabled").lower()
        normalized.append(
            {
                "provider": provider,
                "label": item.get("label") or provider,
                "model": item.get("model") or "",
                "enabled": tier != "disabled",
                "health": "available" if tier != "disabled" else "disabled",
            }
        )
    return normalized


def build_capability_registry(
    workspace: str | Path,
    *,
    readiness: dict[str, Any] | None = None,
    openclaw_status: dict[str, Any] | None = None,
    knowledge_status: dict[str, Any] | None = None,
    provider_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a portable, side-effect-free capability registry."""
    root = Path(workspace).expanduser().resolve()
    readiness = readiness or {}
    openclaw_status = openclaw_status or {}
    knowledge_status = knowledge_status or {}
    provider_status = provider_status or {}

    openclaw_ready = bool(
        openclaw_status.get("ok")
        and openclaw_status.get("task_forwarding_configured")
    )
    n8n_up = bool(
        ((readiness.get("optional_services") or {}).get("n8n") or {}).get("up")
    )
    faiss_ready = bool(knowledge_status.get("faiss_ready"))
    sqlite_ready = bool(knowledge_status.get("sqlite_ready") or knowledge_status.get("ok"))
    providers = _provider_rows(provider_status) if isinstance(provider_status, dict) else []
    cloud_ready = any(bool(item.get("enabled")) for item in providers)

    capabilities = [
        _capability(
            capability_id="perob",
            label="Perob 主系統",
            kind="main_runtime",
            ready=True,
            required=True,
            cost_class="local",
            task_types=["chat", "routing", "health", "frontend"],
            owner_agent="總管中樞",
            endpoint="http://127.0.0.1:5001",
        ),
        _capability(
            capability_id="desktop_bridge",
            label="DesktopBridge 回退橋",
            kind="fallback_bridge",
            ready=True,
            required=True,
            cost_class="local",
            task_types=["chat", "fallback", "local_tools"],
            owner_agent="工程師",
            risk_level="medium",
        ),
        _capability(
            capability_id="openclaw",
            label="OpenClaw Gateway",
            kind="control_plane",
            ready=openclaw_ready,
            status=openclaw_status.get("status") or _status_from_ready(openclaw_ready, degraded=bool(openclaw_status.get("enabled"))),
            required=False,
            cost_class="local",
            task_types=["execution", "debug", "git", "workflow", "security"],
            owner_agent="工程師",
            fallback="desktop_bridge",
            endpoint=f"ws://{openclaw_status.get('host', '127.0.0.1')}:{openclaw_status.get('port', 18789)}",
            task_forwarding_ready=openclaw_ready,
            token_configured=bool(openclaw_status.get("token_configured")),
            forwarding_mode=openclaw_status.get("forwarding_mode", ""),
        ),
        _capability(
            capability_id="lobster",
            label="Lobster 確定性工作流",
            kind="workflow_tool",
            ready=bool(openclaw_ready and openclaw_status.get("lobster_requested", True)),
            required=False,
            cost_class="local",
            task_types=["deterministic_workflow", "approval_checkpoint"],
            risk_level="high",
            owner_agent="帽子",
            fallback="desktop_bridge",
            approval_required=True,
        ),
        _capability(
            capability_id="ollama",
            label="Ollama 本地模型",
            kind="local_model",
            ready=_tcp_up("127.0.0.1", 11434),
            required=False,
            cost_class="local",
            task_types=["discussion", "drafting", "low_cost_reasoning"],
            owner_agent="研究員",
            fallback="free_cloud_provider",
            endpoint="http://127.0.0.1:11434",
        ),
        _capability(
            capability_id="faiss",
            label="FAISS 向量索引",
            kind="memory_index",
            ready=faiss_ready,
            required=False,
            cost_class="local",
            task_types=["retrieval", "long_term_memory"],
            owner_agent="研究員",
            fallback="sqlite_memory",
        ),
        _capability(
            capability_id="sqlite_memory",
            label="SQLite 長期記憶",
            kind="memory_store",
            ready=sqlite_ready,
            required=False,
            cost_class="local",
            task_types=["retrieval", "history", "audit_context"],
            owner_agent="研究員",
        ),
        _capability(
            capability_id="git",
            label="Git 版本真相",
            kind="version_context",
            ready=(root / ".git").exists(),
            required=False,
            cost_class="local",
            task_types=["versioning", "diff_context", "audit"],
            owner_agent="工程師",
        ),
        _capability(
            capability_id="n8n",
            label="n8n 可選排程",
            kind="optional_scheduler",
            ready=n8n_up,
            status="ready" if n8n_up else "degraded_optional",
            required=False,
            cost_class="local",
            task_types=["scheduled_refresh", "reports", "health_check"],
            owner_agent="總管中樞",
            degrades_core_chat=False,
            endpoint="http://127.0.0.1:5678",
        ),
        _capability(
            capability_id="cloud_providers",
            label="雲端模型供應商",
            kind="cloud_llm",
            ready=cloud_ready,
            required=False,
            cost_class="free_or_paid_cloud",
            task_types=["hard_reasoning", "execution", "research"],
            owner_agent="總管中樞",
            fallback="local_models",
            providers=providers,
        ),
    ]
    by_id = {item["id"]: item for item in capabilities}
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "workspace": str(root),
        "policy": {
            "integration_style": "adapter_and_sidecar",
            "main_runtime_rule": "主系統只登記與呼叫能力，不直接塞入重型依賴。",
            "n8n_optional": True,
            "cloud_control_core": "nvidia",
        },
        "capabilities": capabilities,
        "by_id": by_id,
        "summary": {
            "total": len(capabilities),
            "ready": sum(1 for item in capabilities if item.get("ready")),
            "required_ready": all(item.get("ready") for item in capabilities if item.get("required")),
            "local_cost_first": True,
        },
    }


__all__ = ["build_capability_registry"]

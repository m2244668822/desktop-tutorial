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


def _airllm_status(workspace: Path) -> dict[str, Any]:
    venv = workspace / ".venv-airllm"
    python_candidates = [
        venv / "bin" / "python",
        venv / "Scripts" / "python.exe",
    ]
    python_path = next((path for path in python_candidates if path.exists()), None)
    requirements = workspace / "requirements-airllm.txt"
    smoke_test = workspace / "tools" / "airllm_smoke_test.py"
    ready = bool(venv.exists() and python_path and requirements.exists() and smoke_test.exists())
    return {
        "ready": ready,
        "status": "sidecar_ready" if ready else "not_configured",
        "venv": str(venv),
        "python": str(python_path or ""),
        "requirements": str(requirements),
        "smoke_test": str(smoke_test),
        "isolated_runtime": True,
        "runtime_policy": "sidecar_only",
    }


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
    owner_agent: str = "總管中樞",
    fallback: str = "",
    endpoint: str = "",
    **extra: Any,
) -> dict[str, Any]:
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
        "owner_agent": owner_agent,
        "fallback": fallback,
        "endpoint": endpoint,
    }
    payload.update(extra)
    return payload


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

    airllm = _airllm_status(root)
    openclaw_ready = bool(
        openclaw_status.get("ok")
        and openclaw_status.get("task_forwarding_configured")
    )
    n8n_up = bool(
        ((readiness.get("optional_services") or {}).get("n8n") or {}).get("up")
    )
    faiss_ready = bool(knowledge_status.get("faiss_ready"))
    sqlite_ready = bool(knowledge_status.get("sqlite_ready") or knowledge_status.get("ok"))
    providers = provider_status.get("provider_catalog", []) if isinstance(provider_status, dict) else []
    cloud_ready = any(bool(item.get("classification", {}).get("tier") != "disabled") for item in providers)

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
            capability_id="airllm",
            label="AirLLM 側車",
            kind="local_model_sidecar",
            ready=bool(airllm["ready"]),
            status=str(airllm["status"]),
            required=False,
            cost_class="local",
            task_types=["local_inference", "compression", "drafting"],
            owner_agent="研究員",
            fallback="ollama",
            isolated_runtime=bool(airllm["isolated_runtime"]),
            runtime_policy=str(airllm["runtime_policy"]),
            runtime=airllm,
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
            "airllm_sidecar_only": True,
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

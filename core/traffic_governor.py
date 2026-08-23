#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traffic and token-budget routing for the Perob super-platform."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


EXECUTION_TOKENS = {
    "修",
    "修復",
    "修正",
    "debug",
    "bug",
    "程式",
    "前端",
    "後端",
    "server",
    "伺服器",
    "git",
    "workflow",
    "重啟",
    "啟動",
    "部署",
}
SECURITY_TOKENS = {"安全", "駭客", "沙盒", "權限", "token", "憑證", "防火牆"}
RESEARCH_TOKENS = {"論文", "研究", "查詢", "分析", "資料", "rag", "aeg", "知識庫"}
VIDEO_TOKENS = {"影片", "剪輯", "字幕", "配音", "seedance", "動畫"}


def estimate_tokens(text: str) -> int:
    """Cheap deterministic estimate used before deciding whether to call cloud LLMs."""
    clean = str(text or "").strip()
    if not clean:
        return 0
    ascii_chars = len(re.findall(r"[\x00-\x7f]", clean))
    non_ascii_chars = max(0, len(clean) - ascii_chars)
    return max(1, int(ascii_chars / 4) + int(non_ascii_chars / 1.8))


def classify_task(message: str, mode: str = "auto") -> str:
    text = str(message or "").lower()
    normalized_mode = str(mode or "auto").lower()
    if normalized_mode in {"execution", "coding", "workflow"}:
        return "execution"
    if any(token in text for token in SECURITY_TOKENS):
        return "security"
    if any(token in text for token in VIDEO_TOKENS):
        return "video"
    if any(token in text for token in EXECUTION_TOKENS):
        return "execution"
    if any(token in text for token in RESEARCH_TOKENS):
        return "research"
    return "discussion"


def _capability_ready(registry: dict[str, Any] | None, capability_id: str) -> bool:
    if not isinstance(registry, dict):
        return False
    item = (registry.get("by_id") or {}).get(capability_id, {})
    return bool(item.get("ready"))


def decide_route(
    message: str,
    *,
    mode: str = "auto",
    memory_signal: dict[str, Any] | None = None,
    capability_registry: dict[str, Any] | None = None,
    requested_model: str = "auto",
) -> dict[str, Any]:
    """Return the route order and budget policy without calling external services."""
    memory_signal = memory_signal or {}
    capability_registry = capability_registry or {}
    task_type = classify_task(message, mode)
    input_tokens = estimate_tokens(message)
    reasons: list[str] = []
    route_order: list[str] = []

    exact_memory = bool(memory_signal.get("exact_match"))
    memory_confidence = str(memory_signal.get("confidence", "") or "").lower()
    local_memory_ready = exact_memory or memory_confidence in {"high", "direct"}
    openclaw_ready = _capability_ready(capability_registry, "openclaw") and bool(
        ((capability_registry.get("by_id") or {}).get("openclaw") or {}).get(
            "task_forwarding_ready", True
        )
    )
    bridge_ready = _capability_ready(capability_registry, "desktop_bridge") or True
    local_model_ready = _capability_ready(capability_registry, "airllm") or _capability_ready(
        capability_registry, "ollama"
    )
    cloud_ready = _capability_ready(capability_registry, "cloud_providers")

    if local_memory_ready:
        selected_route = "local_memory"
        route_order = ["local_memory", "local_model", "free_cloud_provider"]
        reasons.append("local_memory_exact_match" if exact_memory else "local_memory_high_confidence")
        cloud_allowed = False
        openclaw_allowed = False
    elif task_type in {"execution", "security"}:
        selected_route = "openclaw" if openclaw_ready else "desktop_bridge"
        route_order = ["openclaw", "desktop_bridge", "free_cloud_provider"]
        reasons.append("tool_task_requires_control_plane")
        cloud_allowed = bool(cloud_ready)
        openclaw_allowed = bool(openclaw_ready)
    elif task_type in {"research", "video"}:
        selected_route = "local_memory" if memory_signal.get("source_count") else (
            "local_model" if local_model_ready else "free_cloud_provider"
        )
        route_order = ["local_memory", "local_model", "free_cloud_provider", "paid_cloud_provider"]
        reasons.append("research_or_media_uses_retrieval_first")
        cloud_allowed = bool(cloud_ready)
        openclaw_allowed = False
    else:
        selected_route = "local_model" if local_model_ready else "free_cloud_provider"
        route_order = ["local_memory", "local_model", "free_cloud_provider"]
        reasons.append("discussion_keeps_tools_off_stage")
        cloud_allowed = bool(cloud_ready and not local_model_ready)
        openclaw_allowed = False

    if requested_model and requested_model not in {"auto", selected_route}:
        reasons.append(f"requested_model={requested_model}")

    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "task_type": task_type,
        "selected_route": selected_route,
        "route_order": route_order,
        "reasons": reasons,
        "openclaw_allowed": openclaw_allowed,
        "cloud_allowed": cloud_allowed,
        "paid_cloud_allowed": bool(cloud_allowed and task_type in {"research", "execution", "security"}),
        "n8n_required": False,
        "fallback_is_success": False,
        "budget_policy": {
            "estimated_input_tokens": input_tokens,
            "context_budget_tokens": 1800 if task_type == "discussion" else 3600,
            "local_first": True,
            "exact_memory_skips_cloud": True,
            "paid_cloud_requires": "low_confidence_or_explicit_need",
        },
    }


__all__ = ["classify_task", "decide_route", "estimate_tokens"]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 中樞神經系統（CNS）：

- 統一載入多來源 .env
- 統一供應商狀態快照
- 統一聊天後端調度規則
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    key_name: str
    tier: str


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    provider: str
    label: str
    key: str
    key_name: str
    base_url: str
    base_name: str
    model: str
    model_name: str


PROVIDER_PROFILES: tuple[ProviderProfile, ...] = (
    ProviderProfile("NVIDIA", "NVAPI_API_KEY", "免費額度/主處理"),
    ProviderProfile("Groq", "GROQ_API_KEY", "免費額度"),
    ProviderProfile("Gemini", "GEMINI_API_KEY", "免費額度"),
    ProviderProfile("Google", "GOOGLE_API_KEY", "雲端API/付費或試用"),
    ProviderProfile("OpenAI", "OPENAI_API_KEY", "付費"),
    ProviderProfile("xAI", "XAI_API_KEY", "付費"),
)

RUNTIME_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "nvidia": {
        "label": "NVIDIA",
        "key_names": ("NVAPI_API_KEY", "OPENAI_API_KEY"),
        "base_names": ("NVIDIA_BASE_URL", "OPENAI_BASE_URL"),
        "model_names": ("NVIDIA_MODEL", "OPENAI_MODEL"),
        "default_base": "https://integrate.api.nvidia.com/v1",
        "default_model": "",
    },
    "openai": {
        "label": "OpenAI",
        "key_names": ("OPENAI_API_KEY",),
        "base_names": ("OPENAI_PROVIDER_BASE_URL", "OPENAI_BASE_URL"),
        "model_names": ("OPENAI_PROVIDER_MODEL", "OPENAI_MODEL"),
        "default_base": "https://api.openai.com/v1",
        "default_model": "",
    },
    "groq": {
        "label": "Groq",
        "key_names": ("GROQ_API_KEY",),
        "base_names": ("GROQ_BASE_URL", "OPENAI_BASE_URL"),
        "model_names": ("GROQ_MODEL", "OPENAI_MODEL"),
        "default_base": "https://api.groq.com/openai/v1",
        "default_model": "",
    },
    "gemini": {
        "label": "Gemini",
        "key_names": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "base_names": ("GEMINI_BASE_URL", "OPENAI_BASE_URL"),
        "model_names": ("GEMINI_MODEL", "OPENAI_MODEL"),
        "default_base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "",
    },
}

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


def is_placeholder_value(value: str) -> bool:
    raw = str(value or "").strip().lower()
    return (
        (not raw)
        or ("placeholder" in raw)
        or ("example" in raw)
        or raw.startswith("your_")
        or raw.endswith("_here")
        or raw in {"none", "null", "changeme", "your_api_key"}
    )


def describe_key_state(key: str) -> str:
    clean = str(key or "").strip()
    if not clean:
        return "未設定"
    if is_placeholder_value(clean):
        return "placeholder"
    return f"已設定（長度 {len(clean)}，已遮罩）"


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        raw = value.strip()
        if raw and not raw.startswith(("'", '"')) and "#" in raw:
            raw = raw.split("#", 1)[0].rstrip()
        data[key.strip()] = raw.strip('"').strip("'")
    return data


def load_combined_env(workspace: Path) -> tuple[dict[str, str], Path]:
    primary = workspace / "500" / "llama32-chat" / ".env"
    alias_map = {"GOOLE_API_KEY": "GOOGLE_API_KEY"}
    candidates = [
        workspace / ".env",
        workspace / "500" / "llama32-chat" / ".env",
        workspace / "500" / "llama32-chat" / "config" / ".env",
    ]
    merged: dict[str, str] = {}
    for path in candidates:
        data = load_env(path)
        for key, value in data.items():
            key = alias_map.get(key, key)
            current = merged.get(key, "")
            if key not in merged:
                merged[key] = value
                continue
            if is_placeholder_value(current) and not is_placeholder_value(value):
                merged[key] = value
            elif not current and value:
                merged[key] = value
    return merged, primary


def provider_matrix(env: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in PROVIDER_PROFILES:
        raw_key = str(env.get(profile.key_name, "") or "").strip()
        rows.append(
            {
                "name": profile.name,
                "key_name": profile.key_name,
                "tier": profile.tier,
                "key_state": describe_key_state(raw_key),
                "enabled": bool(raw_key) and not is_placeholder_value(raw_key),
            }
        )
    return rows


def _pick_config_value(
    env: dict[str, str], names: tuple[str, ...], default: str = ""
) -> tuple[str, str]:
    for name in names:
        value = str(os.getenv(name) or env.get(name, "") or "").strip()
        if value and not is_placeholder_value(value):
            return value, name
    return default, (names[0] if names else "")


def resolve_provider_config(workspace: Path, provider: str | None = None) -> dict[str, Any]:
    env, _ = load_combined_env(workspace)
    target = str(provider or "nvidia").strip().lower()
    if target not in RUNTIME_PROVIDER_PROFILES:
        target = "nvidia"

    profile = RUNTIME_PROVIDER_PROFILES[target]
    key, key_name = _pick_config_value(env, profile["key_names"], "")
    base_url, base_name = _pick_config_value(
        env, profile["base_names"], profile["default_base"]
    )
    model, model_name = _pick_config_value(
        env, profile["model_names"], profile["default_model"]
    )
    config = ProviderRuntimeConfig(
        provider=target,
        label=str(profile["label"]),
        key=key,
        key_name=key_name,
        base_url=base_url.rstrip("/") if base_url else "",
        base_name=base_name,
        model=model,
        model_name=model_name,
    )
    return {
        "provider": config.provider,
        "label": config.label,
        "key": config.key,
        "key_name": config.key_name,
        "base_url": config.base_url,
        "base_name": config.base_name,
        "model": config.model,
        "model_name": config.model_name,
    }


def llm_snapshot(workspace: Path) -> dict[str, Any]:
    env, env_path = load_combined_env(workspace)
    nvidia = resolve_provider_config(workspace, "nvidia")
    chosen_key = str(nvidia.get("key", "") or "").strip()
    model = str(nvidia.get("model", "") or "").strip()
    open_source_model = str(
        env.get("OPEN_SOURCE_CHAT_MODEL", env.get("OLLAMA_MODEL", "")) or ""
    ).strip()
    return {
        "env_path": str(env_path),
        "key_source": str(nvidia.get("key_name", "NVAPI_API_KEY")),
        "key_state": describe_key_state(chosen_key),
        "base_url": str(nvidia.get("base_url", "")),
        "model": model or "未設定",
        "open_source_model": open_source_model or "未設定",
        "providers": provider_matrix(env),
    }


def _frontend_provider_enabled(env: dict[str, str], provider_key: str) -> bool:
    if provider_key == "gemini":
        return any(
            bool(env.get(name)) and not is_placeholder_value(str(env.get(name, "")))
            for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY")
        )
    profile = RUNTIME_PROVIDER_PROFILES.get(provider_key)
    if not profile:
        return False
    return any(
        bool(env.get(name)) and not is_placeholder_value(str(env.get(name, "")))
        for name in profile["key_names"]
    )


def frontend_provider_status(workspace: Path) -> dict[str, Any]:
    env, _ = load_combined_env(workspace)
    providers = [
        ("nvidia", "NVIDIA"),
        ("openai", "OpenAI"),
        ("gemini", "Gemini"),
        ("groq", "Groq"),
    ]
    rows = [(key, label, _frontend_provider_enabled(env, key)) for key, label in providers]
    connected = [key for key, _, ok in rows if ok]
    preferred_env = str(env.get("CHAT_PREFERRED_PROVIDER", "") or "").strip().lower()
    if preferred_env in connected:
        preferred = preferred_env
    elif connected:
        preferred = connected[0]
    else:
        preferred = "nvidia"

    catalog = []
    for key, label, ok in rows:
        tier = "primary" if key == preferred and ok else ("enabled" if ok else "disabled")
        catalog.append(
            {
                "key": key,
                "label": label,
                "visible": True,
                "classification": {"tier": tier},
            }
        )

    payload: dict[str, Any] = {
        "chat_preferred_provider": preferred,
        "provider_catalog": catalog,
        "connected_count": len(connected),
        "total_count": len(rows),
    }
    for key, _, ok in rows:
        payload[key] = ok
        payload[f"{key}_key_configured"] = ok
    return payload


def classify_purpose(user_message: str, completed_steps: int = 0, overall_status: str = "") -> str:
    text = (user_message or "").lower()
    if any(token in text for token in EXECUTION_KEYWORDS):
        return "execution"
    status = (overall_status or "").strip().lower()
    if completed_steps > 0 or status in {"success", "partial"}:
        return "execution"
    return "discussion"


def select_backend(purpose: str, snapshot: dict[str, Any]) -> str:
    # 中樞規則：
    # - execution 優先 cloud（若有啟用供應商）
    # - discussion 優先 open_source（若有本地模型）
    # - 否則回 cloud / open_source 的可用方
    providers = snapshot.get("providers", [])
    cloud_ready = any(bool(item.get("enabled")) for item in providers)
    local_ready = str(snapshot.get("open_source_model", "未設定")) not in {"", "未設定"}
    normalized = (purpose or "").strip().lower()
    if normalized == "execution":
        if cloud_ready:
            return "cloud"
        if local_ready:
            return "open_source"
        return "degraded"
    if local_ready:
        return "open_source"
    if cloud_ready:
        return "cloud"
    return "degraded"

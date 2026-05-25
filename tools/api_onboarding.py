#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API onboarding assistant (CLI).

Usage examples:
  python3 tools/api_onboarding.py
  python3 tools/api_onboarding.py --provider nvidia
  python3 tools/api_onboarding.py --workspace /path/to/workspace
"""

from __future__ import annotations

import argparse
from pathlib import Path


ALIAS_KEYS = {"GOOLE_API_KEY": "GOOGLE_API_KEY"}

PROVIDERS = [
    {
        "id": "nvidia",
        "name": "NVIDIA",
        "url": "https://build.nvidia.com/",
        "key_name": "NVAPI_API_KEY",
        "tier": "主處理",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "url": "https://aistudio.google.com/apikey",
        "key_name": "GEMINI_API_KEY",
        "tier": "免費備援",
    },
    {
        "id": "groq",
        "name": "Groq",
        "url": "https://console.groq.com/keys",
        "key_name": "GROQ_API_KEY",
        "tier": "免費備援",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "url": "https://platform.openai.com/api-keys",
        "key_name": "OPENAI_API_KEY",
        "tier": "付費備援",
    },
    {
        "id": "xai",
        "name": "xAI",
        "url": "https://console.x.ai/",
        "key_name": "XAI_API_KEY",
        "tier": "付費備援",
    },
]


def _is_placeholder(raw: str) -> bool:
    text = (raw or "").strip().lower()
    return (
        (not text)
        or ("placeholder" in text)
        or ("example" in text)
        or text.startswith("your_")
    )


def _load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if (not s) or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        raw = value.strip()
        if raw and not raw.startswith(("'", '"')) and "#" in raw:
            raw = raw.split("#", 1)[0].rstrip()
        norm_key = ALIAS_KEYS.get(key.strip(), key.strip())
        data[norm_key] = raw.strip('"').strip("'")
    return data


def load_merged_env(workspace: Path) -> tuple[dict[str, str], Path]:
    primary = workspace / "500" / "llama32-chat" / ".env"
    candidates = [
        workspace / ".env",
        workspace / "500" / "llama32-chat" / ".env",
        workspace / "500" / "llama32-chat" / "config" / ".env",
    ]
    merged: dict[str, str] = {}
    for path in candidates:
        current = _load_env(path)
        for key, value in current.items():
            existing = merged.get(key, "")
            if not existing or (
                _is_placeholder(existing) and not _is_placeholder(value)
            ):
                merged[key] = value
    return merged, primary


def key_state(value: str) -> str:
    if not value:
        return "未設定"
    if _is_placeholder(value):
        return "placeholder"
    return f"已設定（長度 {len(value)}，已遮罩）"


def print_provider_steps(provider: dict, env_path: Path) -> None:
    print(f"=== {provider['name']} ({provider['id']}) ===")
    print(f"申請頁: {provider['url']}")
    print(f"Key 變數: {provider['key_name']}")
    print(f"建議層級: {provider['tier']}")
    print("步驟:")
    print("1. 開啟申請頁建立 API Key。")
    print(f"2. 寫入 {env_path}：{provider['key_name']}=...")
    if provider["id"] == "nvidia":
        print("3. 同步設定 OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1")
        print("4. 同步設定 OPENAI_MODEL=<NVIDIA 可用模型 ID>")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="API onboarding CLI helper.")
    parser.add_argument(
        "--workspace", type=str, default=".", help="Workspace root path."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="",
        help="Provider id: nvidia/gemini/groq/openai/xai",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    env_data, env_path = load_merged_env(workspace)

    selected = (
        [p for p in PROVIDERS if p["id"] == args.provider.lower().strip()]
        if args.provider
        else PROVIDERS
    )
    if args.provider and not selected:
        print(f"Unknown provider: {args.provider}")
        return 1

    print("API Onboarding Summary")
    print(f"Workspace: {workspace}")
    print(f"Primary .env: {env_path}")
    print(f"OPENAI_BASE_URL: {env_data.get('OPENAI_BASE_URL', '未設定')}")
    print(f"OPENAI_MODEL: {env_data.get('OPENAI_MODEL', '未設定')}")
    print("")

    for provider in selected:
        key_value = env_data.get(provider["key_name"], "")
        print_provider_steps(provider, env_path)
        print(f"目前狀態: {key_state(key_value)}")
        print("-" * 60)

    print("")
    print("建議最後檢查：")
    print(f"./.venv/bin/python tools/merge_env_files.py --workspace {workspace}")
    print(
        f"./.venv/bin/python tools/merge_env_files.py --workspace {workspace} --apply"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

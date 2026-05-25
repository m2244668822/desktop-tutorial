#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面端執行環境預檢。

目的：
1. 在啟動前確認桌面 GUI 必要模組是否齊全
2. 檢查工作區整理後是否有關鍵模組斷鏈
3. 回報 Ollama / .env / 模板檔狀態，避免把環境問題誤判成程式 bug
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import platform
import sys
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / "500" / "llama32-chat" / ".env"
ENV_CANDIDATES = [
    BASE_DIR / ".env",
    BASE_DIR / "500" / "llama32-chat" / ".env",
    BASE_DIR / "500" / "llama32-chat" / "config" / ".env",
]
TEMPLATES = [
    BASE_DIR / "templates" / "chat.html",
    BASE_DIR / "templates" / "chat_shell.html",
    BASE_DIR / "templates" / "monitor_shell.html",
    BASE_DIR / "templates" / "agent_shell.html",
]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


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


def load_combined_env() -> tuple[dict[str, str], list[Path]]:
    merged: dict[str, str] = {}
    exists: list[Path] = []
    for path in ENV_CANDIDATES:
        if not path.exists():
            continue
        exists.append(path)
        data = load_env(path)
        for key, value in data.items():
            current = merged.get(key, "")
            if key not in merged:
                merged[key] = value
                continue
            current_is_placeholder = (
                "placeholder" in current.lower() if current else True
            )
            new_is_placeholder = "placeholder" in value.lower() if value else True
            if current_is_placeholder and not new_is_placeholder:
                merged[key] = value
            elif not current and value:
                merged[key] = value
    return merged, exists


def describe_key_state(key: str) -> str:
    if not key:
        return "未設定"
    lower = key.lower()
    if (
        "placeholder" in lower
        or "example" in lower
        or lower.startswith("your_")
        or lower.endswith("_here")
    ):
        return "placeholder"
    if len(key) < 12:
        return "疑似過短"
    return f"已設定（長度 {len(key)}，已遮罩）"


def import_check(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def module_spec_check(module_name: str) -> bool:
    """Fast/non-invasive module availability check.

    Avoids importing heavy modules during health checks.
    """
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def check_ollama(base_url: str) -> tuple[bool, str]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with urllib_request.urlopen(
            urllib_request.Request(url, method="GET"), timeout=1.5
        ):
            return True, ""
    except urllib_error.URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    env_data, env_paths = load_combined_env()
    open_source_url = (
        env_data.get("OPEN_SOURCE_API_URL")
        or env_data.get("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    )
    open_source_model = (
        env_data.get("OPEN_SOURCE_CHAT_MODEL")
        or env_data.get("OLLAMA_MODEL")
        or env_data.get("MODEL")
        or "未設定"
    )
    api_key = env_data.get("NVAPI_API_KEY", env_data.get("OPENAI_API_KEY", ""))
    api_model = env_data.get("OPENAI_MODEL", "")

    critical_errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    infos.append(f"Python: {sys.version.split()[0]}")
    infos.append(f"Platform: {platform.system()} {platform.release()}")
    infos.append(f"Workspace: {BASE_DIR}")

    ok, err = import_check("webview")
    if ok:
        infos.append("pywebview: OK")
    else:
        critical_errors.append(f"pywebview 缺失: {err}")

    if platform.system() == "Darwin":
        ok, err = import_check("objc")
        if ok:
            infos.append("macOS Cocoa backend: OK")
        else:
            critical_errors.append(f"macOS Cocoa backend 缺失: {err}")

    for path in TEMPLATES:
        if not path.exists():
            critical_errors.append(f"缺少模板檔: {path}")

    for module_name in (
        "desktop_chat_app",
        "agent_coordinator",
        "agent_scheduler",
        "agent_self_learning",
    ):
        ok, err = import_check(module_name)
        if ok:
            infos.append(f"{module_name}: import OK")
        else:
            critical_errors.append(f"{module_name}: import 失敗 ({err})")

    for optional_module in (
        "langgraph",
        "langchain",
        "chromadb",
        "sentence_transformers",
    ):
        ok = module_spec_check(optional_module)
        infos.append(f"{optional_module}: {'OK' if ok else '未安裝'}")

    py_ver = sys.version.split()[0]
    if not py_ver.startswith("3.12"):
        warnings.append(
            f"目前 Python={py_ver}；AI/agent 疊代建議固定 .venv Python 3.12"
        )

    if not ENV_FILE.exists():
        warnings.append(f".env 不存在: {ENV_FILE}")
    else:
        infos.append(f"OPEN_SOURCE_CHAT_MODEL: {open_source_model}")
        infos.append(f"OPENAI_MODEL: {api_model or '未設定'}")
        infos.append(f"NV/OpenAI API Key: {describe_key_state(api_key)}")
    if env_paths:
        infos.append("ENV candidates: " + ", ".join(str(p) for p in env_paths))
    else:
        warnings.append("未找到任何 .env 候選檔")

    ollama_ok, ollama_err = check_ollama(open_source_url)
    if ollama_ok:
        infos.append(f"Ollama: OK ({open_source_url})")
    else:
        warnings.append(f"Ollama 未連線 ({open_source_url}): {ollama_err}")

    print("== Desktop Runtime Check ==")
    for item in infos:
        print(f"[INFO] {item}")
    for item in warnings:
        print(f"[WARN] {item}")
    for item in critical_errors:
        print(f"[FAIL] {item}")

    if critical_errors:
        print("\n預檢結果：失敗")
        return 1

    print("\n預檢結果：通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

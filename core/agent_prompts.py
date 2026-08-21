#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體系統提示詞管理 (Agent System Prompts Management)
"""

from __future__ import annotations
import json
from pathlib import Path

from core.trevor_identity import capability_mode_for_alias


AGENT_SYSTEM_PROMPTS = {
    "崔佛": """你是「崔佛」—— 系統唯一公開智能體。
你可依任務切換一般、程式、研究、安全、內容與學習能力模式，但始終以崔佛身份回覆。
NVIDIA 是唯一可規劃、呼叫工具、寫入記憶與執行自主任務的控制核心；其他模型只能對去敏後的對話提供唯讀候選、查錯與潤稿。
回答先給結論與可執行步驟，再說明證據、限制與驗證方法；不確定時必須明示。""",
}

AGENT_WINDOW_ROLES = ("崔佛",)
ONLY_AGENT_ROLES = ("崔佛",)

AGENT_OPERATION_POLICY = """[運作政策]
- 智能體優先：任務先由智能體自行處理，僅在智能體明確無法處理時才升級人工介入。
- 前端訓練優先：指定訓練任務（如躁鬱症發作後、反芻、思緒奔馳）一律先走前端對話實作，不啟動外部程式。
- 外部申請扣分：每次申請外部程式或外部代理，需標記問題代碼並扣 10 分，由後端政策引擎留下紀錄。
- 生活化回答：醫療心理教育要先同理，再用生活比喻解釋，不做診斷承諾。"""

AGENT_PROFILE_DIRNAME = "agent_profiles"
AGENT_PROFILE_FILES = {
    "崔佛": "prophet_profile.json",
}
GLOBAL_CHATGPT_PROMPT_FILE = "global_chatgpt_prompt.md"
SYNCED_CHATGPT_PROMPT_FILE = "synced_chatgpt_custom_instructions.md"
GLOBAL_CHATGPT_PROMPT_MAX_CHARS = 2400


def load_agent_prompt_profiles(workspace: Path) -> dict[str, dict]:
    """從工作區加載特定智能體的 Profile 配置"""
    profiles = {}
    profile_dir = workspace / "config" / AGENT_PROFILE_DIRNAME
    if not profile_dir.is_dir():
        return profiles

    for role, filename in AGENT_PROFILE_FILES.items():
        p_path = profile_dir / filename
        if p_path.exists():
            try:
                profiles[role] = json.loads(p_path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return profiles


def load_global_agent_prompt(workspace: Path) -> str:
    """加載全局自定義指令 (Custom Instructions)"""
    candidates = [
        workspace / SYNCED_CHATGPT_PROMPT_FILE,
        workspace / GLOBAL_CHATGPT_PROMPT_FILE,
        workspace / "config" / GLOBAL_CHATGPT_PROMPT_FILE,
    ]
    for path in candidates:
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text[:GLOBAL_CHATGPT_PROMPT_MAX_CHARS]
            except Exception:
                pass
    return ""


def get_agent_system_prompt(role: str, workspace: Path | None = None) -> str:
    """獲取指定角色的系統提示詞，並整合 Profile 與全局指令"""
    capability_mode = capability_mode_for_alias(role)
    base_prompt = AGENT_SYSTEM_PROMPTS["崔佛"]
    base_prompt = f"{base_prompt}\n\n[能力模式]\n{capability_mode}\n\n{AGENT_OPERATION_POLICY}"
    
    if workspace:
        global_prompt = load_global_agent_prompt(workspace)
        if global_prompt:
            base_prompt = f"{base_prompt}\n\n[全局指令]\n{global_prompt}"
            
        profiles = load_agent_prompt_profiles(workspace)
        if "崔佛" in profiles:
            p_data = profiles["崔佛"]
            p_text = json.dumps(p_data, ensure_ascii=False, indent=2)
            base_prompt = f"{base_prompt}\n\n[角色 Profile]\n{p_text}"
            
    return base_prompt

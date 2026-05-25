#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體系統提示詞管理 (Agent System Prompts Management)
"""

from __future__ import annotations
import json
from pathlib import Path


AGENT_SYSTEM_PROMPTS = {
    "總管": """你是「總管」—— 具備巡查與調度能力的深度思考助手。
你的特質：理解用戶需求、監控系統健康、主動調度多智能體協作。
重要規則：參考巡查快照，若系統不穩定須優先告知；每次回覆要展現思考過程與多方觀點。""",
    "研究員": """你是「研究員」—— 具備巡查意識的開源技術分析師。
任務：提供客觀比較、檢視系統資料庫完整性。回覆時若發現資料缺失或 API 異常，須主動警示。""",
    "工程師": """你是「工程師」—— 永續掌控前後端的主責修繕智能體。
核心職責：
1) 任何程式相關問題（前端、後端、路由、事件、資料流、部署、效能）都要主動接手修復與 Debug。
2) 可主動回報目前狀態、風險、修復進度，不可只被動等待。
3) 若資訊不足，先反查 Git 與其他智能體線索，再提出修復方案，不可直接跳過。
4) 可主動參考開源項目與網路解法，但需先說明採用原因與風險。
5) 與「帽子」保持安全對接：所有高風險變更需先請帽子做沙盒推演，再落地。
6) 若仍受阻，提出「最小必要權限請求」與下一步（例如 SMP、多進程、外部代理）。
補充規範：
- 前端註解、錯誤提示與操作建議一律繁體中文。
- 回覆要先給可執行動作，再給原因與驗證方法。""",
    "中繼器": """你是「中繼器」—— 負責多智能體通訊巡查的戰略顧問。
任務：綜觀全局、識別溝通缺口。主動在各角色間傳遞關鍵訊息，確保系統巡查結果被落實。""",
    "小編": """你是「小編」—— 內容與文案編輯專員。
任務：優化文案、彙整巡查與協作報告。將枯燥的系統狀態轉化為易懂的提醒，並主動建議協作流。""",
    "申言者": """你是「申言者」—— 程式與人的第一道風險分級中樞（最高權限治理角色）。
核心職責：
1) 先做危險等級分類（L0/L1/L2/L3），不可只攔截後卡住。
2) 一旦判定含安全風險，必須回傳「帽子」做沙盒測試與許可流程。
3) 取得帽子回傳許可後，必須再打回對應主責（通常工程師）執行，不可中斷流程。
4) 針對人機互動衝突、價值衝突、越權指令，提供可執行的替代方案與邊界說明。
5) 重大事件要留下可追蹤記錄（風險等級、判定原因、交接對象、解封條件）。""",
    "帽子": """你是「帽子」—— 網路安全與沙盒推演主責智能體。
核心職責：
1) 針對申言者回傳的高風險請求，先進行沙盒推演與攻防驗證，再決定是否放行。
2) 任務包含阻擋駭客入侵、噪音流量、異常請求、權限濫用。
3) 你可調動高權限資源，但必須先經過沙盒驗證並留下審計紀錄。
4) 安全結論需可被工程師直接執行：提供封鎖規則、修補建議、回歸測試清單。
5) 與工程師協作時，以「安全優先、可落地」為原則，避免只給抽象警告。""",
}

AGENT_WINDOW_ROLES = ("研究員", "工程師", "中繼器", "小編", "申言者", "帽子")
ONLY_AGENT_ROLES = ("總管", "研究員", "工程師", "中繼器", "小編", "申言者", "帽子")

AGENT_PROFILE_DIRNAME = "agent_profiles"
AGENT_PROFILE_FILES = {
    "申言者": "prophet_profile.json",
    "總管": "autonomous_manager_profile.json",
    "通用": "autonomous_manager_profile.json",
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
    base_prompt = AGENT_SYSTEM_PROMPTS.get(role, AGENT_SYSTEM_PROMPTS["總管"])
    
    if workspace:
        global_prompt = load_global_agent_prompt(workspace)
        if global_prompt:
            base_prompt = f"{base_prompt}\n\n[全局指令]\n{global_prompt}"
            
        profiles = load_agent_prompt_profiles(workspace)
        if role in profiles:
            p_data = profiles[role]
            p_text = json.dumps(p_data, ensure_ascii=False, indent=2)
            base_prompt = f"{base_prompt}\n\n[角色 Profile]\n{p_text}"
            
    return base_prompt

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prophet-to-engineer collaboration bridge.

This module turns conversational intent into an engineering handoff while
preserving the prophet role's original risk/governance duties.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


MOC_LINKS = {
    "architecture": "05_MOC_架構群組_2026-05-26",
    "ops": "06_MOC_運維群組_2026-05-26",
    "training": "07_MOC_訓練群組_2026-05-26",
    "handoff": "12_基礎啟動與文件治理交接_2026-05-27",
}

POLICY_LINKS = {
    "single_entry": "ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25",
    "mac_windows": "ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK",
    "startup_encoding": "ProjectDocs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27",
}

REPORT_LINKS = {
    "md_bundle": "ProjectDocs/dev/MD_BUNDLE_INDEX_2026-05-27",
    "architecture_audit": "ProjectDocs/dev/ARCHITECTURE_BASELINE_AND_MD_BUNDLE_AUDIT_2026-05-27",
    "progress_p0": "ProjectDocs/dev/MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26",
}


def _clean_text(value: Any, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:limit]


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def is_prophet_engineer_request(message: str, role: str = "") -> bool:
    """Return true when a turn should create a prophet->engineer handoff."""
    text = str(message or "")
    role_name = str(role or "").strip()
    if role_name == "申言者":
        return True
    if "申言者" in text and "工程師" in text:
        return True
    handoff_tokens = (
        "語譯",
        "轉譯",
        "翻譯成寫程式",
        "寫程式的語",
        "工程語",
        "工程師開始",
        "修改資料進度",
        "每日最低標準",
        "對話回寫",
        "神經連結",
    )
    return _contains_any(text, handoff_tokens)


def classify_risk(message: str) -> str:
    text = str(message or "").lower()
    if _contains_any(text, ("reset --hard", "rm -rf", "delete from", "drop table", "清空資料", "刪除資料")):
        return "L3"
    if _contains_any(text, ("git push", "覆蓋", "永久", "資料庫", "權限", "token", "api key")):
        return "L2"
    if _contains_any(text, ("修改", "寫程式", "debug", "啟動", "前端", "後端", "git", "n8n")):
        return "L1"
    return "L0"


def classify_graph_group(message: str, keywords: list[str] | None = None) -> str:
    text = " ".join([str(message or ""), " ".join(keywords or [])]).lower()
    if _contains_any(text, ("api", "入口", "前端", "後端", "路由", "架構", "拓撲", "gateway")):
        return "architecture"
    if _contains_any(text, ("git", "啟動", "n8n", "端口", "環境", "救援", "windows", "mac")):
        return "ops"
    if _contains_any(text, ("訓練", "記憶", "rag", "faiss", "sqlite", "回覆", "對話", "神經")):
        return "training"
    return "ops"


def build_prophet_engineer_handoff(
    message: str,
    role: str,
    analysis: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
    retrieval_brief: str = "",
) -> dict[str, Any]:
    """Build a structured handoff payload for runtime JSONL and UI metadata."""
    analysis = analysis or {}
    keywords = [str(k) for k in (keywords or []) if str(k).strip()]
    topic = _clean_text(analysis.get("primary_topic") or message, limit=80)
    risk_level = classify_risk(message)
    group = classify_graph_group(message, keywords)
    now = datetime.now().isoformat()

    doc_links = {
        "moc": MOC_LINKS[group],
        "handoff": MOC_LINKS["handoff"],
        "policy": POLICY_LINKS["single_entry"]
        if group == "architecture"
        else POLICY_LINKS["mac_windows"],
        "report": REPORT_LINKS["architecture_audit"]
        if group in {"architecture", "ops"}
        else REPORT_LINKS["md_bundle"],
    }

    engineering_task = (
        "把使用者想法轉成可執行變更：先確認不覆蓋未提交資料，"
        "再更新程式/文件/測試，最後回寫 turn 與 edge JSONL。"
    )
    if group == "architecture":
        engineering_task = (
            "檢查單一入口、前後端路由與 API 契約；修改時維持 5001 gateway，"
            "並以測試驗證 /chat/agent 與 /api/send_message 相容。"
        )
    elif group == "ops":
        engineering_task = (
            "確認 Git、啟動腳本、n8n、端口與跨系統路徑；只做可回溯修改，"
            "不得覆蓋本機未提交或未確認資料。"
        )
    elif group == "training":
        engineering_task = (
            "強化對話回寫、關鍵字檢索、記憶邊界與回覆多樣性；訓練資料保持 overlay，"
            "不可污染主系統穩定層。"
        )

    handoff = {
        "timestamp": now,
        "mode": "prophet_engineer_bridge",
        "capability_scope": "additive_only",
        "requested_role": str(role or "總管"),
        "topic": topic,
        "risk_level": risk_level,
        "graph_group": group,
        "primary_tags": [group, "prophet-engineer", "dialog-backwrite"],
        "secondary_tags": ["daily-minimum-links", "positive-edge", "utf8"],
        "prophet_translation": (
            "申言者原職責保留：先做風險分級、邊界判讀與必要安全交接。"
            "工程語譯只是額外能力，用來把已判讀的想法轉成工程師可執行約束。"
        ),
        "engineer_task": engineering_task,
        "acceptance_criteria": [
            "新產出的筆記至少有 3 條功能性連結：MOC、技術政策、任務/報告。",
            "檔名不可使用未命名；標題需包含主題與日期。",
            "每輪重要對話需回寫 turn/edge JSONL，保留可檢索關係。",
            "修改前先看 Git 狀態，不覆蓋未提交資料。",
        ],
        "doc_links": doc_links,
        "retrieval_brief": _clean_text(retrieval_brief, limit=220),
        "handoff_state": "queued_for_engineer",
        "requires_hat_review": risk_level in {"L2", "L3"},
    }
    return handoff


def render_prophet_engineer_base_reply(handoff: dict[str, Any]) -> str:
    """Render a deterministic prophet reply before any free-form LLM text."""
    risk_level = handoff.get("risk_level", "L0") if isinstance(handoff, dict) else "L0"
    graph_group = handoff.get("graph_group", "ops") if isinstance(handoff, dict) else "ops"
    hat_review = bool(handoff.get("requires_hat_review")) if isinstance(handoff, dict) else False
    review_line = (
        "這一輪需要先交給帽子做安全覆核，工程師只能在覆核通過後執行。"
        if hat_review
        else "這一輪不需要帽子先擋下，但工程師仍要照 Git 狀態與測試結果執行。"
    )
    return (
        "【申言者】我先把你的想法整理成固定交接單，不讓模型自由亂寫不存在的範例程式。\n"
        "- 原本能力保留：風險分級、邊界判讀、必要時交給帽子覆核。\n"
        "- 新增能力：把你的語意翻成工程師可以直接改檔、測試、回寫的任務格式。\n"
        f"- 本輪分級：{risk_level}；主幹群組：{graph_group}。\n"
        f"- 覆核規則：{review_line}"
    )


def render_prophet_engineer_reply(base_reply: str, handoff: dict[str, Any]) -> str:
    """Append a concise handoff block without hiding the original reply."""
    base = str(base_reply or "").strip()
    if "[申言者->工程師交接]" in base:
        return base
    links = handoff.get("doc_links", {}) if isinstance(handoff, dict) else {}
    criteria = handoff.get("acceptance_criteria", []) if isinstance(handoff, dict) else []
    criteria_text = "\n".join(f"- {item}" for item in criteria[:4])
    block = (
        "[申言者->工程師交接]\n"
        f"- 風險級別：{handoff.get('risk_level', 'L0')}\n"
        f"- 主幹群組：{handoff.get('graph_group', 'ops')}\n"
        f"- 工程語譯：{handoff.get('engineer_task', '')}\n"
        f"- 必連 MOC：[[{links.get('moc', MOC_LINKS['ops'])}]]\n"
        f"- 必連政策：[[{links.get('policy', POLICY_LINKS['mac_windows'])}]]\n"
        f"- 必連報告：[[{links.get('report', REPORT_LINKS['architecture_audit'])}]]\n"
        "[驗收條件]\n"
        f"{criteria_text}"
    ).strip()
    if not base:
        return f"【申言者】我已把你的想法轉成工程師可執行語譯。\n{block}"
    return f"{base}\n\n{block}"

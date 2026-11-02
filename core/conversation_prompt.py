"""Compact conversation instructions shared by Trevor model providers."""

from __future__ import annotations

from typing import Mapping


_LESSON_FIELDS = {
    "event": ("事件", "實際發生了什麼？"),
    "expectation": ("家庭期待／外部要求", "你感受到哪些期待或要求？"),
    "inner_content": ("內在語句／聲音／想法", "當時腦中出現了什麼？"),
    "evidence": ("證據與其他解釋", "目前有哪些證據，以及可能的其他解釋？"),
    "next_step": ("下一個安全可逆的小行動", "你願意先做哪一個安全、可逆的小步驟？"),
}


def build_recovery_lesson_prompt(
    field: str,
    record: Mapping[str, str],
    *,
    faith_opt_in: bool = False,
    safety_hold: bool = False,
) -> str:
    """Build a bounded, non-diagnostic prompt for the first recovery lesson."""
    selected_field = str(field or "")
    if selected_field not in _LESSON_FIELDS:
        selected_field = "event"

    known_values = []
    for key, (label, _) in _LESSON_FIELDS.items():
        value = record.get(key, "")
        rendered = str(value).strip() if value is not None else ""
        known_values.append(f"{label}：{rendered or '未知'}")

    prompt = (
        "你正在陪伴使用者完成第一課的五格整理。請用自然、尊重的繁體中文回應，"
        "只把以下紀錄當作使用者已提供的資料，不補寫或推測未知內容。\n"
        "[目前紀錄]\n"
        + "\n".join(known_values)
        + "\n\n"
        "遵守界線：不診斷；不把感受直接判定為外部事實；不得把內在聲音當成權威指示或外部訊息。"
        "家庭壓力可能是脈絡之一，不得說成唯一病因。不得用任何信念或宗教語言取代安全判斷。"
        "每輪最多提出一個問題，不連問、不要求一次完成多格。"
    )

    if safety_hold:
        return (
            prompt
            + "\n\n[安全暫停] 先停止課程，不要繼續課程，也不要要求填寫下一格。"
            "先確認你現在是否安全；以簡短、直接、不帶判斷的方式詢問。"
        )

    label, question = _LESSON_FIELDS[selected_field]
    prompt += (
        f"\n\n[本輪焦點] 只處理「{label}」。先承接使用者已說的內容，"
        f"再用這一個問題邀請補充：{question}"
    )
    if faith_opt_in:
        prompt += (
            "\n\n若使用者主動選擇，可提供可選的意義整理框架，例如聖經中的觀點；"
            "這只是個人反思材料，不具權威，也不代表對事件或內在經驗的事實判定。"
            "使用者可以拒絕、退出或設下界線，不要勸服。"
        )
    return prompt

_CAPABILITY_HINTS = {
    "general": "以一般對談能力回應。",
    "coding": "需要程式內容時給正確、可驗證的實作，但不要假裝已執行工具。",
    "research": "區分事實、推論與未知；需要即時資料時明說必須查證。",
    "security": "優先說清楚風險、權限與可回復性，不誇大威脅。",
    "content": "保留使用者原意與語氣，產出可直接使用的內容。",
    "learning": "依使用者程度拆解概念，用例子協助建立可重用理解。",
}


def build_trevor_system_prompt(
    capability_mode: str = "general",
    *,
    safety_nudge: str = "",
) -> str:
    capability = _CAPABILITY_HINTS.get(
        str(capability_mode or "general").strip().lower(),
        _CAPABILITY_HINTS["general"],
    )
    prompt = (
        "你是崔佛，是同一位能自然對話、分析並協助工作的繁體中文智能體。"
        "先直接回應使用者此刻真正想談的內容，不輸出角色標籤、巡檢報告、固定步驟或制式結尾。"
        "一般談話不要任務化，也不要宣稱已執行任何工具。"
        "先描述經驗本身並暫緩武斷解釋；只有資訊不足且會改變答案時，才指出不清楚的是哪一層並問一個短問題。"
        "需要時才用定義、拆解、層級、反例、回推、對齊、蒸餾、重構與收束；複雜回答最後要看得出結構，短對話維持自然。"
        "可以質疑邏輯或隱含假設，但不要否定使用者這個人。能形成可複用判準或語句時再提供。"
        "遇到重要決策，交代近期效果、下一層可能後果，以及忽略時的隱性風險。"
        "只有前一個說法真的有偏差時才簡短自我修正，不做表演式反思。"
        "談到心理或身體經驗時保持描述性、不診斷、不奪權，並留下可回轉空間。"
        f"{capability}"
    )
    if safety_nudge:
        prompt += (
            "\n\n[本輪安全觀察]\n"
            f"{safety_nudge}\n"
            "請先對齊感受，再自然地帶出一次這個提醒；不要把它說成診斷或確定事實。"
        )
    return prompt


__all__ = ["build_trevor_system_prompt", "build_recovery_lesson_prompt"]

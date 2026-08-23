#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Message semantics analysis for Chinese-first interactive agent workflows."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[\u4e00-\u9fff]{2,4}")
ACTION_TOKENS = (
    "建立",
    "執行",
    "修復",
    "修正",
    "解決",
    "優化",
    "安裝",
    "整理",
    "產生",
    "寫入",
    "部署",
    "補齊",
    "落實",
    "處理",
    "分派",
    "指派",
)
QUESTION_TOKENS = (
    "請問",
    "想問",
    "詢問",
    "如何",
    "為什麼",
    "怎麼",
    "是否",
    "嗎",
    "？",
    "?",
)
API_TOKENS = (
    "api",
    "endpoint",
    "token",
    "apikey",
    "api key",
    "sdk",
    "headers",
    "base_url",
    "openai",
    "openrouter",
    "gemini",
    "groq",
    "huggingface",
    "串接",
    "金鑰",
    "模型",
    "供應商",
    "rate limit",
)
CODEX_TOKENS = (
    "codex",
    "快速整合",
    "快車道",
    "工程模式",
    "執行優先",
)
STATUS_TOKENS = (
    "狀態",
    "進度",
    "回報",
    "更新到哪",
    "完成了嗎",
    "running",
    "pending",
    "status",
    "throughput",
    "吞吐",
)
SHORT_COMMAND_TOKENS = (
    "修復",
    "修正",
    "解決",
    "補齊",
    "同步",
    "更新",
    "回報",
    "執行",
    "開啟",
    "繼續",
    "處理",
)
CONNECTORS = (
    "跟",
    "與",
    "和",
    "及",
    "或",
    "或者",
    "還是",
    "比較",
    "關係",
    "之間",
    "對照",
)
STOPWORDS = {
    "我",
    "我們",
    "你",
    "你們",
    "他們",
    "一下",
    "希望",
    "現在",
    "可以",
    "請",
    "幫我",
    "這個",
    "那個",
    "就是",
    "以及",
    "還有",
    "目前",
    "需要",
}
DOMAIN_KEYWORDS = {
    "語言比對": (
        "語言",
        "語意",
        "semantic",
        "nlp",
        "比對",
        "檢索",
        "embedding",
        "向量",
    ),
    "腦科學": ("腦科學", "神經科學", "神經", "大腦", "認知"),
    "心理學": ("心理學", "心理", "情緒", "行為", "人格"),
    "程式工程": (
        "程式",
        "程式碼",
        "前端",
        "後端",
        "api",
        "框架",
        "部署",
        "bug",
        "修復",
    ),
    "智能體編排": (
        "智能體",
        "agent",
        "langgraph",
        "workflow",
        "router",
        "planner",
        "verifier",
        "memory",
    ),
    "文案編輯": ("文案", "改寫", "標題", "摘要", "小編", "語氣"),
    "資料記憶": ("知識庫", "記憶", "rag", "faiss", "sqlite", "向量"),
    "網路安全": (
        "安全",
        "漏洞",
        "滲透",
        "攻擊",
        "入侵",
        "掃描",
        "防火牆",
        "封鎖",
        "xss",
        "sql injection",
        "csrf",
        "cors",
        "sandbox",
    ),
    "倫理道德": (
        "倫理",
        "道德",
        "價值",
        "善惡",
        "信仰",
        "聖經",
        "經文",
        "先知",
        "申言者",
        "以利亞",
        "elijah",
        "告解",
    ),
}
RADICAL_GROUPS = {
    "心": "心想念思意情感憶恐悲憂快慢懂慧慮",
    "言": "言語話說論討講詢訊詞詩讀註譯請",
    "手": "手打提推按接援控擴擇措",
    "木": "木機框構模樣本根",
    "月": "月腦肺肝胃肌脂臟",
    "水": "水流海源波深清況",
}
ROLE_HINTS = {
    "語言比對": "研究員",
    "腦科學": "研究員",
    "心理學": "研究員",
    "程式工程": "工程師",
    "智能體編排": "中繼器",
    "文案編輯": "小編",
    "資料記憶": "工程師",
    "網路安全": "帽子",
    "倫理道德": "申言者",
}


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text or "")


def _extract_keywords(text: str, max_items: int = 8) -> list[str]:
    lowered_text = (text or "").lower()
    domain_hits: list[str] = []
    for keywords in DOMAIN_KEYWORDS.values():
        for keyword in keywords:
            if keyword.lower() in lowered_text and keyword not in domain_hits:
                domain_hits.append(keyword)

    tokens = []
    for token in _tokenize(text):
        clean = token.strip().lower()
        if not clean:
            continue
        if clean in STOPWORDS or clean in CONNECTORS:
            continue
        if len(clean) == 1 and not clean.isascii():
            continue
        tokens.append(clean)
    freq = Counter(tokens)
    sorted_tokens = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    ranked = domain_hits + [t for t, _ in sorted_tokens if t not in domain_hits]
    return ranked[:max_items]


def _detect_domains(text: str) -> list[str]:
    lowered = (text or "").lower()
    tags = []
    for tag, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            tags.append(tag)
    return tags


def _detect_connectors(text: str) -> list[str]:
    return [word for word in CONNECTORS if word in (text or "")]


def _map_mode_hint(raw_hint: str) -> str:
    hint = str(raw_hint or "").strip().lower()
    if not hint:
        return ""

    alias_map = {
        "codex_fast": (
            "codex_fast",
            "codex",
            "quick_exec",
            "quick_integrate",
            "快速整合",
            "快車道",
        ),
        "api_query": ("api_query", "api", "endpoint", "串接", "金鑰", "模型"),
        "status_check": ("status_check", "status", "progress", "進度", "狀態", "回報"),
        "task_request": ("task_request", "task", "任務", "執行", "修復", "處理"),
        "discussion": ("discussion", "討論", "聊天", "想法"),
    }
    for mode, aliases in alias_map.items():
        if any(alias in hint for alias in aliases):
            return mode
    return ""


def _detect_intent(text: str) -> str:
    raw = text or ""
    lowered = raw.lower()
    has_question = any(token in raw for token in QUESTION_TOKENS) or any(
        token in lowered for token in QUESTION_TOKENS
    )
    has_action = any(token in raw for token in ACTION_TOKENS) or any(
        token in lowered for token in ACTION_TOKENS
    )
    if has_action:
        return "action"
    if has_question:
        return "question"
    return "discussion"


def _detect_interaction_mode(text: str, intent: str) -> tuple[str, str]:
    source = (text or "").strip()
    lowered = source.lower()
    if not source:
        return "discussion", "semantic_module"

    explicit_patterns = (
        r"(?:上下文|context|互動模式|interaction[_\s-]*mode|mode|模式)\s*[:：]\s*([^\n，。；;|]+)",
        r"(?:intent)\s*[:：]\s*([^\n，。；;|]+)",
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if not match:
            continue
        hinted = _map_mode_hint(match.group(1))
        if hinted:
            return hinted, "semantic_context_hint"

    scores = {
        "codex_fast": 0,
        "task_request": 0,
        "status_check": 0,
        "api_query": 0,
        "discussion": 0,
    }
    if intent == "action":
        scores["task_request"] += 4
        scores["codex_fast"] += 2
    if intent == "question":
        scores["discussion"] += 1
        scores["api_query"] += 1
        scores["status_check"] += 1

    for token in ACTION_TOKENS:
        if token.lower() in lowered:
            scores["task_request"] += 2
            scores["codex_fast"] += 1
    for token in API_TOKENS:
        if token.lower() in lowered:
            scores["api_query"] += 2
    for token in CODEX_TOKENS:
        if token.lower() in lowered:
            scores["codex_fast"] += 5
    for token in STATUS_TOKENS:
        if token.lower() in lowered:
            scores["status_check"] += 2

    if re.search(r"\b(get|post|put|delete|patch)\b", lowered):
        scores["api_query"] += 4
    if re.search(r"\b(status|progress|throughput|latency)\b", lowered):
        scores["status_check"] += 2
    if len(source) <= 10 and any(token in source for token in SHORT_COMMAND_TOKENS):
        scores["task_request"] += 3
        scores["codex_fast"] += 2

    top_score = max(scores.values())
    if top_score <= 0:
        return "discussion", "semantic_module"
    winners = [mode for mode, score in scores.items() if score == top_score]
    for mode in (
        "codex_fast",
        "task_request",
        "status_check",
        "api_query",
        "discussion",
    ):
        if mode in winners:
            return mode, "semantic_module"
    return "discussion", "semantic_module"


def _detect_radicals(text: str, max_items: int = 4) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not text:
        return result
    for radical, chars in RADICAL_GROUPS.items():
        matches = sorted({ch for ch in text if ch in chars})
        if matches:
            result.append({"radical": radical, "chars": matches, "count": len(matches)})
    result.sort(key=lambda x: (-int(x["count"]), x["radical"]))
    return result[:max_items]


def _suggest_roles(domain_tags: list[str], intent: str) -> list[str]:
    hints = ["申言者"]
    for tag in domain_tags:
        role = ROLE_HINTS.get(tag)
        if role and role not in hints:
            hints.append(role)
    if intent == "action" and "工程師" not in hints:
        hints.append("工程師")
    if intent == "question" and "研究員" not in hints:
        hints.append("研究員")
    return hints[:4]


def analyze_message(text: str) -> dict[str, Any]:
    source = (text or "").strip()
    keywords = _extract_keywords(source)
    connectors = _detect_connectors(source)
    domain_tags = _detect_domains(source)
    intent = _detect_intent(source)
    radicals = _detect_radicals(source)
    role_hints = _suggest_roles(domain_tags, intent)
    interaction_mode, interaction_mode_source = _detect_interaction_mode(source, intent)
    primary_topic = keywords[0] if keywords else ""
    return {
        "intent": intent,
        "primary_topic": primary_topic,
        "keywords": keywords,
        "connectors": connectors,
        "domain_tags": domain_tags,
        "radical_patterns": radicals,
        "role_hints": role_hints,
        "interaction_mode": interaction_mode,
        "interaction_mode_source": interaction_mode_source,
        "analyzed_at": datetime.now().isoformat(),
    }

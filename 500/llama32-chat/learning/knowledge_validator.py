#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KnowledgeValidator — 雙層知識驗證
對應 KAL Loop「驗證」節點 (Gemma + Claude)

由於本機無 Gemma 26B，使用：
  主驗證：ollama（mistral / llama3.2）
  二次驗證：Anthropic Claude API（可選，需 ANTHROPIC_API_KEY）

判定邏輯：
  PASS  — 通過，可寫入永久知識庫
  RETRY — 資訊不足，觸發「不夠→再學」
  REJECT — 品質太低或矛盾，丟棄
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import ollama

logger = logging.getLogger("knowledge_validator")

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent

# ── 驗證結果 ─────────────────────────────────────────────────


@dataclass
class ValidationResult:
    verdict: str  # "PASS" | "RETRY" | "REJECT"
    score: float  # 0.0 ~ 1.0
    reason: str
    validated_by: str  # "ollama" | "claude" | "rule"
    timestamp: str = ""

    def __post_init__(self):
        self.timestamp = datetime.now().isoformat()

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    @property
    def needs_retry(self) -> bool:
        return self.verdict == "RETRY"


# ── Prompt ───────────────────────────────────────────────────

_VALIDATE_PROMPT = """\
你是嚴格的知識品質審核員。評估以下知識片段：

主題：{topic}
摘要：{summary}
事實：{facts}
可信度：{confidence}

請評估：
1. 資訊是否充足（非空洞泛論）
2. 是否有明顯錯誤或矛盾
3. 是否與主題相關

輸出嚴格 JSON（不要 markdown）：
{{"verdict": "PASS|RETRY|REJECT", "score": 0.0-1.0, "reason": "原因（50字以內）"}}

PASS = 資訊充足且正確
RETRY = 資訊不足，需要補充
REJECT = 錯誤、矛盾或完全無關"""


# ── 主驗證器（ollama）────────────────────────────────────────


class OllamaValidator:
    def __init__(self, model: str = "mistral"):
        self.model = model

    def validate(self, wiki: dict) -> ValidationResult:
        prompt = _VALIDATE_PROMPT.format(
            topic=wiki.get("topic", ""),
            summary=wiki.get("summary", ""),
            facts="; ".join(wiki.get("key_facts", [])[:5]),
            confidence=wiki.get("confidence", 0.5),
        )
        try:
            resp = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0, "num_predict": 256},
            )
            text = resp["message"]["content"].strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                verdict = data.get("verdict", "RETRY").upper()
                if verdict not in ("PASS", "RETRY", "REJECT"):
                    verdict = "RETRY"
                return ValidationResult(
                    verdict=verdict,
                    score=float(data.get("score", 0.5)),
                    reason=data.get("reason", ""),
                    validated_by=f"ollama/{self.model}",
                )
        except Exception as e:
            logger.debug("ollama 驗證失敗: %s", e)
        return self._rule_fallback(wiki)

    def _rule_fallback(self, wiki: dict) -> ValidationResult:
        conf = float(wiki.get("confidence", 0.5))
        summary_len = len(wiki.get("summary", ""))
        facts_count = len(wiki.get("key_facts", []))
        if conf < 0.3 or summary_len < 20:
            return ValidationResult("REJECT", conf, "可信度過低或摘要過短", "rule")
        if facts_count == 0 or summary_len < 50:
            return ValidationResult("RETRY", conf, "資訊不足，需補充", "rule")
        return ValidationResult("PASS", conf, "規則驗證通過", "rule")


# ── 二次驗證器（Claude）──────────────────────────────────────


class ClaudeValidator:
    """Claude API 二次驗證，僅在 ollama 結果為邊界值時觸發。"""

    _THRESHOLD = 0.6  # score < 0.6 才觸發 Claude 二次確認

    def __init__(self):
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._available = bool(self._api_key)
        if not self._available:
            logger.debug("ANTHROPIC_API_KEY 未設定，Claude 驗證停用")

    def validate(self, wiki: dict, first_result: ValidationResult) -> ValidationResult:
        if not self._available:
            return first_result
        if first_result.score >= self._THRESHOLD:
            return first_result  # 分數夠高，不需二次確認

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            prompt = (
                f"以下知識片段的第一次審核結果為：{first_result.verdict}（{first_result.reason}）\n\n"
                f"主題：{wiki.get('topic')}\n摘要：{wiki.get('summary')}\n\n"
                "請給出最終判定（PASS/RETRY/REJECT）和簡短理由，"
                '只輸出 JSON：{"verdict": "...", "reason": "..."}'
            )
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                verdict = data.get("verdict", first_result.verdict).upper()
                return ValidationResult(
                    verdict=verdict,
                    score=first_result.score,
                    reason=data.get("reason", first_result.reason),
                    validated_by="claude",
                )
        except Exception as e:
            logger.debug("Claude 驗證失敗: %s", e)
        return first_result


# ── 統一入口 ─────────────────────────────────────────────────


class KnowledgeValidator:
    """
    呼叫 validate(wiki) 取得 ValidationResult。
    自動組合 ollama 主驗證 + Claude 二次驗證。
    """

    def __init__(self, primary_model: str = "mistral"):
        # 優先用 mistral（更強），若不可用降級 llama3.2
        self._primary = OllamaValidator(model=primary_model)
        self._secondary = ClaudeValidator()

    def validate(self, wiki: dict) -> ValidationResult:
        first = self._primary.validate(wiki)
        final = self._secondary.validate(wiki, first)
        logger.info(
            "驗證 [%s] → %s (score=%.2f) by %s",
            wiki.get("topic", "?"),
            final.verdict,
            final.score,
            final.validated_by,
        )
        return final

    def validate_batch(self, wikis: list) -> dict:
        passed, retried, rejected = [], [], []
        for wiki in wikis:
            r = self.validate(wiki)
            if r.passed:
                passed.append(wiki)
            elif r.needs_retry:
                retried.append(wiki)
            else:
                rejected.append(wiki)
        logger.info(
            "批次驗證: PASS=%d RETRY=%d REJECT=%d",
            len(passed),
            len(retried),
            len(rejected),
        )
        return {"passed": passed, "retry": retried, "rejected": rejected}

"""Promotion and retrieval policy for Trevor's long-term memory."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MemoryDecision:
    promote: bool
    categories: tuple[str, ...] = ()
    reason: str = "transient_turn"
    sensitive: bool = False

    def public_dict(self) -> dict:
        return asdict(self)


class MemoryPromotionPolicy:
    """Promote durable user-owned facts instead of saving every chat turn."""

    _EXPLICIT = ("請記住", "幫我記住", "記住這件事", "存成長期記憶", "加入長期記憶")
    _RETRIEVAL = (
        "之前",
        "上次",
        "我們說過",
        "你還記得",
        "照原本",
        "照先前",
        "根據過去",
        "延續前面",
        "繼續我們",
        "接續之前",
    )
    _SENSITIVE = (
        "自殺",
        "自傷",
        "傷害自己",
        "傷害別人",
        "資訊都在對我說話",
        "專門對我說話",
        "在對我說話",
        "只有我能完成使命",
        "被選中",
        "天命",
        "診斷",
        "病歷",
    )

    def should_retrieve(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        return bool(text) and any(token.lower() in text for token in self._RETRIEVAL)

    def assess(self, message: str) -> MemoryDecision:
        text = str(message or "").strip()
        lowered = text.lower()
        sensitive = any(token.lower() in lowered for token in self._SENSITIVE)
        if not text:
            return MemoryDecision(False, sensitive=sensitive)

        categories: list[str] = []
        explicit = any(token in text for token in self._EXPLICIT)
        if explicit:
            categories.append("explicit")
        if re.search(r"(?:我|我們).{0,10}(?:偏好|喜歡|習慣|不喜歡|希望你)", text):
            categories.append("preference")
        if re.search(r"(?:之後|以後|往後).{0,18}(?:回答|回覆|請|都|不要|要)", text):
            categories.append("standing_preference")
        if re.search(r"(?:我們)?(?:已)?決定(?:採用|使用|改成|選擇)?", text):
            categories.append("decision")
        if re.search(r"(?:長期)?目標(?:是|為|：|:)", text):
            categories.append("goal")
        if re.search(
            r"(?:(?:以後|之後|往後|你|崔佛|回覆時).{0,12}(?:必須|務必)|請遵守|固定遵守)",
            text,
        ):
            categories.append("standing_constraint")

        unique = tuple(dict.fromkeys(categories))
        if sensitive and not explicit:
            return MemoryDecision(
                False,
                categories=unique,
                reason="sensitive_requires_confirmation",
                sensitive=True,
            )
        if unique:
            return MemoryDecision(
                True,
                categories=unique,
                reason="durable_user_information",
                sensitive=sensitive,
            )
        return MemoryDecision(False, sensitive=sensitive)


__all__ = ["MemoryDecision", "MemoryPromotionPolicy"]

"""Non-diagnostic, session-scoped safety signal tracking."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from threading import RLock
from time import monotonic


@dataclass(frozen=True)
class SafetyAssessment:
    categories: tuple[str, ...] = ()
    strength: int = 0
    should_nudge: bool = False
    urgent: bool = False
    nudge: str = ""
    diagnosis: str = ""

    def public_dict(self) -> dict:
        return asdict(self)


class SafetySignalTracker:
    """Track observations without turning them into diagnoses or identities."""

    _WINDOW_SECONDS = 6 * 60 * 60
    _DIRECT_REFERENTIAL = re.compile(
        r"(?:新聞|電視|廣告|歌曲|資訊|訊息|演算法|ai|宇宙).{0,12}"
        r"(?:專門)?(?:在)?對我(?:說話|傳訊|暗示)",
        re.IGNORECASE,
    )
    _MEANING_LINKAGE = re.compile(
        r"(?:所有|全部|每一個|到處).{0,12}(?:都)?(?:和我有關|指向我|暗示我)",
        re.IGNORECASE,
    )
    _MISSION_STRONG = re.compile(
        r"(?:只有我能|我被選中|非我不可|天命|世界需要我)", re.IGNORECASE
    )
    _MISSION_WEAK = re.compile(
        r"(?:很大的使命|使命感|責任感.{0,6}(?:突然|變得|很高|升高))", re.IGNORECASE
    )
    _URGENT = re.compile(
        r"(?:想死|不想活|自殺|傷害自己|殺了自己|傷害別人|控制不住.{0,8}(?:傷害|攻擊))",
        re.IGNORECASE,
    )

    def __init__(self):
        self._events: dict[str, deque[tuple[float, str, int]]] = defaultdict(deque)
        self._lock = RLock()

    @staticmethod
    def _session_key(session_id: str | None) -> str:
        return str(session_id or "").strip()[:128] or "default"

    def _signals(self, text: str) -> list[tuple[str, int]]:
        signals: list[tuple[str, int]] = []
        if self._URGENT.search(text):
            signals.append(("immediate_danger", 3))
        if self._DIRECT_REFERENTIAL.search(text):
            signals.append(("referential_message", 2))
        if self._MEANING_LINKAGE.search(text):
            signals.append(("meaning_overconnection", 2))
        if self._MISSION_STRONG.search(text):
            signals.append(("mission_escalation", 2))
        elif self._MISSION_WEAK.search(text):
            signals.append(("mission_escalation", 1))
        return signals

    def assess(self, session_id: str | None, message: str) -> SafetyAssessment:
        text = str(message or "").strip()
        current = self._signals(text)
        if not current:
            return SafetyAssessment()

        key = self._session_key(session_id)
        now = monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0][0] > self._WINDOW_SECONDS:
                events.popleft()
            for category, strength in current:
                events.append((now, category, strength))
            totals: dict[str, int] = defaultdict(int)
            for _, category, strength in events:
                totals[category] += strength

        categories = tuple(dict.fromkeys(category for category, _ in current))
        urgent = "immediate_danger" in categories
        should_nudge = urgent or any(totals[category] >= 2 for category in categories)
        nudge = ""
        if urgent:
            nudge = (
                "安全提醒：如果你現在可能傷害自己或別人，先離開危險物品，"
                "聯絡一位能到場的人或當地緊急服務；這件事不用自己扛。"
            )
        elif should_nudge and "mission_escalation" in categories:
            nudge = (
                "小提醒：如果使命感或責任感突然比平常高很多，先暫緩重大承諾與不可逆決定，"
                "把它當成需要休息、記錄與驗證的訊號，而不是現在就必須服從的命令。"
            )
        elif should_nudge:
            nudge = (
                "小提醒：先把「資訊像在特別對你說話」當成目前很真實的感受，"
                "但暫時不要把它判定為事實；可以記下原始資訊、其他解釋，以及最近睡眠或壓力的變化。"
            )
        return SafetyAssessment(
            categories=categories,
            strength=max(strength for _, strength in current),
            should_nudge=should_nudge,
            urgent=urgent,
            nudge=nudge,
        )


__all__ = ["SafetyAssessment", "SafetySignalTracker"]

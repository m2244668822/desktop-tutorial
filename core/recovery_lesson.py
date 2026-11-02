from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Mapping

from core.safety_signals import SafetyAssessment

LESSON_ID = "recovery_lesson_1_pressure_is_not_command"
FIELD_ORDER = ("event", "expectation", "inner_content", "evidence", "next_step")
_FIELD_LABELS = {
    "event": "事件",
    "expectation": "家庭期待／外部要求",
    "inner_content": "內在語句／聲音／想法",
    "evidence": "證據與其他解釋",
    "next_step": "下一個安全可逆的小行動",
}
_PROMPTS = {
    "event": "先從事件開始：實際發生了什麼？",
    "expectation": "接著看家庭期待／外部要求：你感受到哪些期待或要求？",
    "inner_content": "再記下內在語句／聲音／想法：當時腦中出現什麼？",
    "evidence": "接著看證據與其他解釋：目前有哪些證據，以及可能的其他解釋？",
    "next_step": "最後想一個下一個安全可逆的小行動：你願意先做哪一小步？",
}
_OMISSION = re.compile(r"^[\s\W_]+$", re.UNICODE)
_OMISSION_WORDS = {"略", "跳過", "不想說", "先不說"}


@dataclass(frozen=True)
class FiveFieldRecord:
    event: str = ""
    expectation: str = ""
    inner_content: str = ""
    evidence: str = ""
    next_step: str = ""


@dataclass(frozen=True)
class LessonState:
    lesson_id: str = LESSON_ID
    current_field: str = "event"
    record: FiveFieldRecord = FiveFieldRecord()
    completed: bool = False
    faith_opt_in: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "lesson_id": self.lesson_id,
            "current_field": self.current_field,
            "record": {field.name: getattr(self.record, field.name) for field in fields(self.record)},
            "completed": self.completed,
            "faith_opt_in": self.faith_opt_in,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "LessonState":
        raw_record = value.get("record", {})
        if not isinstance(raw_record, Mapping):
            raise ValueError("record must be a mapping")
        record = FiveFieldRecord(**{
            name: str(raw_record.get(name, "")) for name in FIELD_ORDER
        })
        lesson_id = str(value.get("lesson_id", LESSON_ID))
        current_field = str(value.get("current_field", "event"))
        if lesson_id != LESSON_ID or current_field not in FIELD_ORDER:
            raise ValueError("invalid lesson state")
        return cls(
            lesson_id=lesson_id,
            current_field=current_field,
            record=record,
            completed=bool(value.get("completed", False)),
            faith_opt_in=bool(value.get("faith_opt_in", False)),
        )


@dataclass(frozen=True)
class LessonTurn:
    status: str
    reply: str
    state: LessonState
    lesson_context: str = ""


class RecoveryLessonEngine:
    def is_start_request(self, message: str) -> bool:
        text = str(message or "").strip()
        if re.search(
            r"(?:不要|先不要|暫時不要|別|不想|不用).{0,4}(?:開始|進入|做|上)?\s*第一課",
            text,
        ):
            return False
        return bool(re.search(r"(?:開始|開始第一課|第一課|進入第一課|做第一課)", text))

    def start(self, *, faith_opt_in: bool = False) -> LessonTurn:
        state = LessonState(faith_opt_in=faith_opt_in)
        return LessonTurn("active", _PROMPTS["event"], state)

    def accept(
        self,
        message: str,
        state: LessonState,
        safety: SafetyAssessment,
    ) -> LessonTurn:
        assessment = safety
        if assessment.urgent:
            return LessonTurn("safety_hold", assessment.nudge or "先確認安全。", state)

        raw = str(message or "")
        trimmed = raw.strip()
        context = ""
        if assessment.categories and any(category in {
            "referential_message", "meaning_overconnection", "mission_escalation"
        } for category in assessment.categories):
            context = f"使用者原文：{raw}\n先分離感受與證據，不確認外部意義。"

        if not trimmed or _OMISSION.fullmatch(trimmed) or trimmed in _OMISSION_WORDS:
            return LessonTurn("active", _PROMPTS[state.current_field], state, context)
        if state.completed:
            return LessonTurn("completed", self._summary(state), state, context)
        if state.lesson_id != LESSON_ID or state.current_field not in FIELD_ORDER:
            raise ValueError("invalid lesson state")

        values = {name: getattr(state.record, name) for name in FIELD_ORDER}
        values[state.current_field] = raw
        index = FIELD_ORDER.index(state.current_field)
        complete = index == len(FIELD_ORDER) - 1
        next_field = state.current_field if complete else FIELD_ORDER[index + 1]
        new_state = LessonState(
            lesson_id=state.lesson_id,
            current_field=next_field,
            record=FiveFieldRecord(**values),
            completed=complete,
            faith_opt_in=state.faith_opt_in,
        )
        if complete:
            return LessonTurn("completed", self._summary(new_state), new_state, context)
        return LessonTurn("active", _PROMPTS[next_field], new_state, context)

    @staticmethod
    def _summary(state: LessonState) -> str:
        lines = [f"{_FIELD_LABELS[name]}：{getattr(state.record, name)}" for name in FIELD_ORDER]
        return "第一課整理（依照你的原文）：\n" + "\n".join(lines)


__all__ = [
    "LESSON_ID", "FIELD_ORDER", "FiveFieldRecord", "LessonState",
    "LessonTurn", "RecoveryLessonEngine",
]

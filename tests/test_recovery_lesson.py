from core.recovery_lesson import FIELD_ORDER, LESSON_ID, RecoveryLessonEngine
from core.safety_signals import SafetyAssessment


def test_start_returns_first_field_prompt():
    turn = RecoveryLessonEngine().start()
    assert turn.status == "active"
    assert turn.state.current_field == "event"
    assert "實際發生了什麼" in turn.reply


def test_unlabelled_answer_is_saved_only_to_current_field():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    turn = engine.accept("昨天家人問我什麼時候才像個正常人", state)
    assert turn.state.record.event == "昨天家人問我什麼時候才像個正常人"
    assert turn.state.record.expectation == ""
    assert turn.state.current_field == "expectation"


def test_blank_answer_does_not_advance_or_invent_content():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    turn = engine.accept("...", state)
    assert turn.state.current_field == "event"
    assert turn.state.record.event == ""


def test_urgent_safety_signal_holds_lesson_before_llm():
    safety = SafetyAssessment(categories=("immediate_danger",), strength=3,
                              should_nudge=True, urgent=True, nudge="先確認安全。")
    engine = RecoveryLessonEngine()
    turn = engine.accept("我現在可能傷害自己", engine.start().state, safety)
    assert turn.status == "safety_hold"
    assert turn.state.current_field == "event"
    assert "先確認安全" in turn.reply
    assert not turn.lesson_context


def test_completion_keeps_user_values_as_raw_text():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    for value in ["事件", "家人期待", "我腦中出現的語句", "目前沒有外部證據", "先去散步十分钟"]:
        turn = engine.accept(value, state)
        state = turn.state
    assert turn.status == "completed"
    assert turn.state.record.next_step == "先去散步十分钟"


def test_start_detection_and_faith_opt_in_boundary():
    engine = RecoveryLessonEngine()
    assert engine.is_start_request("開始第一課")
    turn = engine.start()
    assert not turn.state.faith_opt_in
    assert all(word not in turn.reply + turn.lesson_context for word in ("聖經", "神", "寬恕", "贖罪", "悔改"))


def test_state_round_trip_and_nonurgent_referential_constraint():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    restored = type(state).from_dict(state.to_dict())
    safety = SafetyAssessment(categories=("referential_message",), strength=2)
    turn = engine.accept("電視像在對我說話", restored, safety)
    assert turn.state.record.event == "電視像在對我說話"
    assert "先分離感受與證據，不確認外部意義" in turn.lesson_context
    assert "電視像在對我說話" in turn.lesson_context


def test_public_contract_constants():
    assert LESSON_ID == "recovery_lesson_1_pressure_is_not_command"
    assert FIELD_ORDER == ("event", "expectation", "inner_content", "evidence", "next_step")


def test_non_opted_in_completion_preserves_raw_text_without_added_faith_frame():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    values = ["事件", "外部要求", "神像在說話", "證據", "散步"]
    for value in values:
        turn = engine.accept(value, state)
        state = turn.state
    assert turn.state.record.inner_content == "神像在說話"
    assert "神像在說話" in turn.reply
    assert all(word not in turn.reply for word in ("聖經", "寬恕", "贖罪", "悔改"))

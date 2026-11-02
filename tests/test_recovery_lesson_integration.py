import pytest

from core.interaction_gateway import InteractionDecision
from core.recovery_lesson import LESSON_ID
from desktop_chat_app import DesktopBridge


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(DesktopBridge, "start_background_monitor", lambda self: None)
    instance = DesktopBridge(workspace=tmp_path)
    instance.enable_live_llm_default = False
    return instance


@pytest.mark.parametrize("start_text", ["開始第一課", "開始壓力不是命令", "做五格紀錄"])
def test_start_request_creates_lesson_state_and_returns_first_question(bridge, start_text):
    result = bridge.send_message(start_text, session_id="lesson")

    assert result["lesson"] == {
        "id": LESSON_ID,
        "status": "active",
        "current_field": "event",
        "record": {
            "event": "", "expectation": "", "inner_content": "", "evidence": "", "next_step": "",
        },
    }
    assert "實際發生了什麼" in result["reply"]
    assert bridge.session_store.lesson_state("lesson")["current_field"] == "event"
    assert not result["workflow_ran"]


def test_active_lesson_saves_raw_answer_and_advances_one_field(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    captured = {}

    def local_reply(messages):
        captured["messages"] = messages
        return "收到。我們接著看外部期待。", {"ok": True, "provider": "open_source"}

    monkeypatch.setattr(bridge, "_call_ollama_chat", local_reply)
    bridge.enable_live_llm_default = True
    result = bridge.send_message("  昨天家人問我進度  ", session_id="lesson", model_key="open_source")

    assert result["lesson"]["current_field"] == "expectation"
    assert result["lesson"]["record"]["event"] == "  昨天家人問我進度  "
    assert result["lesson"]["record"]["expectation"] == ""
    assert result["reply"] == "收到。我們接著看外部期待。"
    assert "[本輪焦點]" in captured["messages"][0]["content"]
    assert "家庭期待／外部要求" in captured["messages"][0]["content"]


def test_urgent_safety_bypasses_llm_and_returns_safety_hold(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    bridge.enable_live_llm_default = True
    monkeypatch.setattr(bridge, "_generate_live_llm_reply", lambda **kwargs: pytest.fail("LLM called"))
    monkeypatch.setattr(bridge.interaction_gateway, "decide", lambda *args, **kwargs: pytest.fail("router called"))

    result = bridge.send_message("我現在想傷害自己", session_id="lesson")

    assert result["lesson"]["status"] == "safety_hold"
    assert result["lesson"]["current_field"] == "event"
    assert result["lesson"]["record"]["event"] == ""
    assert result["safety"]["urgent"]
    assert "安全提醒" in result["reply"]
    assert "實際發生了什麼" not in result["reply"]
    assert not result["workflow_ran"]


def test_lesson_state_is_not_promoted_to_long_term_memory(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    monkeypatch.setattr(bridge, "_persist_promoted_memory", lambda **kwargs: pytest.fail("memory promoted"))
    monkeypatch.setattr(bridge, "_persist_training_overlay_sample", lambda **kwargs: pytest.fail("overlay written"))

    result = bridge.send_message("請記住：我偏好先慢慢說", session_id="lesson")

    assert result["lesson"]["record"]["event"] == "請記住：我偏好先慢慢說"
    assert result["memory"]["promotion"]["promote"] is False
    assert result["memory"]["promotion"]["saved"] is False
    assert result["memory"]["saved"] is False


def test_non_lesson_message_keeps_existing_route_behavior(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "_generate_live_llm_reply", lambda **kwargs: (
        "照原本的對話繼續。", {"ok": True, "attempted": True, "provider": "open_source"},
    ))

    result = bridge.send_message("今天想聊聊近況", session_id="ordinary")

    assert result["interaction"]["route"] == "conversation"
    assert result["reply"] == "照原本的對話繼續。"
    assert bridge.session_store.lesson_state("ordinary") is None
    assert "lesson" not in result


def test_unrelated_start_request_does_not_open_lesson(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "_generate_live_llm_reply", lambda **kwargs: (
        "開始吧。", {"ok": True, "attempted": True, "provider": "open_source"},
    ))

    result = bridge.send_message("開始整理我的筆記", session_id="ordinary")

    assert "lesson" not in result
    assert bridge.session_store.lesson_state("ordinary") is None


def test_completed_lesson_releases_next_turn_to_normal_route(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    for answer in ("事件", "期待", "心裡的話", "其他解釋", "先休息"):
        result = bridge.send_message(answer, session_id="lesson")
    assert result["lesson"]["status"] == "completed"
    monkeypatch.setattr(bridge, "_generate_live_llm_reply", lambda **kwargs: (
        "回到一般聊天。", {"ok": True, "attempted": True, "provider": "open_source"},
    ))

    next_result = bridge.send_message("今天還有別的事", session_id="lesson")

    assert "lesson" not in next_result
    assert next_result["reply"] == "回到一般聊天。"


def test_lesson_falls_back_to_engine_reply_when_llm_fails(bridge):
    bridge.send_message("做五格紀錄", session_id="lesson")

    result = bridge.send_message("昨天與家人談到工作", session_id="lesson")

    assert result["lesson"]["current_field"] == "expectation"
    assert "你感受到哪些期待或要求" in result["reply"]
    assert result["llm_live"]["fallback_used"]


def test_lesson_falls_back_to_engine_reply_when_llm_raises(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    monkeypatch.setattr(
        bridge, "_generate_live_llm_reply",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    result = bridge.send_message("昨天與家人談到工作", session_id="lesson")

    assert result["lesson"]["current_field"] == "expectation"
    assert "你感受到哪些期待或要求" in result["reply"]
    assert result["llm_live"]["fallback_used"]


def test_pending_clarification_takes_precedence_over_lesson(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    bridge.session_store.set_pending_interaction(
        "lesson", kind="clarification", original_message="這個任務範圍不清楚", question="要改哪裡？"
    )
    monkeypatch.setattr(bridge, "_generate_live_llm_reply", lambda **kwargs: (
        "先處理原本的澄清。", {"ok": True, "attempted": True, "provider": "open_source"},
    ))

    result = bridge.send_message("先改登入流程", session_id="lesson")

    assert result["reply"] == "先處理原本的澄清。"
    assert bridge.session_store.lesson_state("lesson")["record"]["event"] == ""


def test_pending_confirmation_takes_precedence_over_lesson(bridge, monkeypatch):
    bridge.send_message("開始第一課", session_id="lesson")
    bridge.session_store.set_pending_action("lesson", "幫我檢查系統狀態")
    seen = {}

    def decide(message, **kwargs):
        seen.update(message=message, confirmed=kwargs["confirmed"])
        return InteractionDecision(route="conversation", purpose="discussion", capability_mode="general")

    monkeypatch.setattr(bridge.interaction_gateway, "decide", decide)
    monkeypatch.setattr(bridge, "_generate_live_llm_reply", lambda **kwargs: (
        "已收到確認。", {"ok": True, "attempted": True, "provider": "open_source"},
    ))

    result = bridge.send_message("確認執行", session_id="lesson")

    assert seen == {"message": "幫我檢查系統狀態", "confirmed": True}
    assert "lesson" not in result
    assert bridge.session_store.lesson_state("lesson")["record"]["event"] == ""


def test_nonurgent_safety_signal_keeps_one_field_progression(bridge):
    bridge.send_message("開始第一課", session_id="lesson")

    result = bridge.send_message("電視像在對我說話", session_id="lesson")

    assert result["lesson"]["record"]["event"] == "電視像在對我說話"
    assert result["lesson"]["current_field"] == "expectation"
    assert result["safety"]["should_nudge"]
    assert "先把「資訊像在特別對你說話」當成目前很真實的感受" in result["reply"]


def test_lesson_context_is_optional_for_normal_chat_messages(bridge):
    messages = bridge._build_live_llm_messages("申言者", "你好")

    assert "[本輪焦點]" not in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "你好"}

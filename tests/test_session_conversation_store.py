from core.session_context import SessionConversationStore


def test_sessions_are_isolated():
    store = SessionConversationStore(max_messages=12)
    store.append_turn("session-a", "A 的問題", "A 的回答")
    store.append_turn("session-b", "B 的問題", "B 的回答")

    a_text = [item["content"] for item in store.messages("session-a")]
    b_text = [item["content"] for item in store.messages("session-b")]

    assert a_text == ["A 的問題", "A 的回答"]
    assert b_text == ["B 的問題", "B 的回答"]


def test_client_history_only_hydrates_an_empty_session():
    store = SessionConversationStore(max_messages=12)
    supplied = [
        {"role": "user", "text": "前一題"},
        {"role": "assistant", "text": "前一答"},
    ]

    assert store.hydrate("session-a", supplied)
    assert not store.hydrate(
        "session-a", [{"role": "user", "text": "不應覆蓋伺服器內容"}]
    )
    assert [item["content"] for item in store.messages("session-a")] == [
        "前一題",
        "前一答",
    ]


def test_pending_action_is_scoped_to_its_session():
    store = SessionConversationStore()
    store.set_pending_action("session-a", "刪除舊資料")

    assert store.pending_action("session-a") == "刪除舊資料"
    assert store.pending_action("session-b") == ""
    assert store.take_pending_action("session-a") == "刪除舊資料"
    assert store.pending_action("session-a") == ""


def test_pending_interaction_preserves_clarification_context():
    store = SessionConversationStore()
    store.set_pending_interaction(
        "session-a",
        kind="clarification",
        original_message="幫我處理一下",
        question="請告訴我要處理的目標。",
    )

    assert store.pending_interaction("session-a") == {
        "kind": "clarification",
        "original_message": "幫我處理一下",
        "question": "請告訴我要處理的目標。",
        "options": [],
        "required_confirmation": False,
    }
    assert store.take_pending_interaction("session-a")["original_message"] == "幫我處理一下"
    assert store.pending_interaction("session-a") is None


def test_lesson_state_isolated_by_session():
    store = SessionConversationStore()
    state = {
        "situation": "收到主管批評",
        "emotion": "焦慮",
        "automatic_thought": "我一定做不好",
        "evidence_for": ["主管指出一處錯誤"],
        "evidence_against": ["其他部分有完成"],
    }

    store.set_lesson_state("session-a", state)

    assert store.lesson_state("session-a") == state
    assert store.lesson_state("session-b") is None


def test_lesson_state_is_returned_as_deep_copy():
    store = SessionConversationStore()
    state = {"reflection": {"observations": ["先描述經驗"]}}
    store.set_lesson_state("session-a", state)

    returned = store.lesson_state("session-a")
    returned["reflection"]["observations"].append("修改回傳值")

    assert store.lesson_state("session-a") == {
        "reflection": {"observations": ["先描述經驗"]}
    }


def test_clear_lesson_state_does_not_clear_messages():
    store = SessionConversationStore()
    store.append_turn("session-a", "保留這段對話", "收到")
    store.set_lesson_state("session-a", {"situation": "待整理"})

    store.clear_lesson_state("session-a")

    assert store.lesson_state("session-a") is None
    assert [item["content"] for item in store.messages("session-a")] == [
        "保留這段對話",
        "收到",
    ]


def test_unknown_session_has_no_lesson_state():
    store = SessionConversationStore()

    assert store.lesson_state("never-seen") is None

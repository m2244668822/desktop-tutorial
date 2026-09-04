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

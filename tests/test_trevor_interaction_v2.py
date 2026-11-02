from unittest import mock
from pathlib import Path

from desktop_chat_app import DesktopBridge


def _bridge():
    bridge = DesktopBridge(energy_lite=True)
    bridge.memory_manager = None
    bridge._run_keyword_retrieval = lambda *_args, **_kwargs: {
        "ok": True,
        "matches": [],
        "match_count": 0,
    }
    bridge._record_turn_artifacts = lambda **_kwargs: None
    bridge._persist_training_overlay_sample = lambda **_kwargs: None
    bridge._should_attempt_live_llm_backend = lambda _backend: True
    return bridge


def test_energy_lite_disables_memory_autosave(monkeypatch):
    import desktop_chat_app

    class MemoryManagerSpy:
        instances = []

        def __init__(self, *args, **kwargs):
            self.auto_save = kwargs["auto_save"]
            self.instances.append(self)

        def get_conversation_history(self, **_kwargs):
            return []

        def save_ide_context(self, _context):
            return None

    monkeypatch.setattr(desktop_chat_app, "AgentMemoryManager", MemoryManagerSpy)
    bridge = desktop_chat_app.DesktopBridge(workspace=Path.cwd(), energy_lite=True)
    try:
        assert MemoryManagerSpy.instances[-1].auto_save is False
    finally:
        bridge.stop_background_monitor()


def test_bridge_keeps_model_context_isolated_by_session():
    bridge = _bridge()
    captured = []

    def fake_reply(**kwargs):
        captured.append(list(kwargs["conversation_context"]))
        return "自然回答", {"ok": True, "attempted": True, "provider": "open_source"}

    bridge._generate_live_llm_reply = fake_reply
    try:
        bridge.send_message("A 的秘密", session_id="a", model_key="open_source")
        bridge.send_message("B 的問題", session_id="b", model_key="open_source")
        bridge.send_message("接著呢", session_id="a", model_key="open_source")
    finally:
        bridge.stop_background_monitor()

    assert captured[0] == []
    assert captured[1] == []
    assert [item["content"] for item in captured[2]] == ["A 的秘密", "自然回答"]


def test_bridge_hydrates_frontend_history_for_a_new_session():
    bridge = _bridge()
    captured = {}

    def fake_reply(**kwargs):
        captured["conversation"] = kwargs["conversation_context"]
        return "接續回答", {"ok": True, "attempted": True, "provider": "open_source"}

    bridge._generate_live_llm_reply = fake_reply
    try:
        bridge.send_message(
            "那接下來呢？",
            session_id="hydrated",
            model_key="open_source",
            conversation=[
                {"role": "user", "text": "我們正在整理框架"},
                {"role": "assistant", "text": "先建立互動契約"},
            ],
        )
    finally:
        bridge.stop_background_monitor()

    assert [item["content"] for item in captured["conversation"]] == [
        "我們正在整理框架",
        "先建立互動契約",
    ]


def test_bridge_does_not_retrieve_or_persist_ordinary_chat():
    bridge = _bridge()
    memory = mock.Mock()
    bridge.memory_manager = memory
    bridge._generate_live_llm_reply = lambda **_kwargs: (
        "嗨，今天想聊什麼？",
        {"ok": True, "attempted": True, "provider": "open_source"},
    )
    retrieval = mock.Mock(return_value={"ok": True, "matches": [], "match_count": 0})
    bridge._run_keyword_retrieval = retrieval
    try:
        result = bridge.send_message("你好", session_id="chat", model_key="open_source")
    finally:
        bridge.stop_background_monitor()

    assert result["interaction"]["route"] == "conversation"
    assert result["memory"]["retrieval_attempted"] is False
    assert result["memory"]["saved"] is False
    retrieval.assert_not_called()
    memory.save_conversation.assert_not_called()


def test_bridge_promotes_durable_preference_only():
    bridge = _bridge()
    memory = mock.Mock()
    bridge.memory_manager = memory
    bridge._generate_live_llm_reply = lambda **_kwargs: (
        "知道了，以後先講結論。",
        {"ok": True, "attempted": True, "provider": "open_source"},
    )
    try:
        result = bridge.send_message(
            "之後回答都先講結論", session_id="preference", model_key="open_source"
        )
    finally:
        bridge.stop_background_monitor()

    assert result["memory"]["saved"] is True
    memory.save_conversation.assert_called_once()


def test_failed_model_call_is_not_replaced_by_a_fake_conversation_template():
    bridge = _bridge()
    bridge._generate_live_llm_reply = lambda **_kwargs: (
        "",
        {
            "ok": False,
            "attempted": True,
            "provider": "open_source",
            "fallback_reason": "timeout",
        },
    )
    try:
        result = bridge.send_message(
            "你倒是回答我問的東西啊", session_id="failed-model", model_key="open_source"
        )
    finally:
        bridge.stop_background_monitor()

    assert "固定模板冒充回覆" in result["reply"]
    assert "輕量對談模式" not in result["reply"]
    assert "你一句「執行」" not in result["reply"]


def test_high_risk_confirmation_replays_only_the_pending_session_action():
    bridge = _bridge()
    workflow_result = {
        "route": "崔佛",
        "result": "已完成經確認的操作",
        "verification_notes": "驗證完成",
        "task_state": {
            "overall_status": "success",
            "completed_steps": 1,
            "failed_steps": 0,
        },
    }
    try:
        first = bridge.send_message("刪除舊資料", session_id="risk")
        unrelated = bridge.send_message("確認執行", session_id="other")
        with mock.patch("core.langgraph_workflow.run_workflow", return_value=workflow_result) as run:
            confirmed = bridge.send_message("確認執行", session_id="risk")
    finally:
        bridge.stop_background_monitor()

    assert first["completion"]["state"] == "awaiting_confirmation"
    assert unrelated["interaction"]["reason"] == "confirmation_without_pending_action"
    assert confirmed["interaction"]["route"] == "task"
    assert confirmed["workflow_ran"] is True
    run.assert_called_once_with("刪除舊資料", workspace=str(bridge.workspace))


def test_clarification_reply_resumes_original_target_in_same_session():
    bridge = _bridge()
    workflow_result = {
        "route": "崔佛",
        "result": "已完成檢查",
        "verification_notes": "測試狀態已確認",
        "task_state": {
            "overall_status": "success",
            "completed_steps": 1,
            "failed_steps": 0,
        },
    }
    try:
        first = bridge.send_message("幫我處理一下", session_id="resume")
        with mock.patch("core.langgraph_workflow.run_workflow", return_value=workflow_result) as run:
            resumed = bridge.send_message(
                "目前這個 repo，直接檢查測試", session_id="resume"
            )
    finally:
        bridge.stop_background_monitor()

    assert first["completion"]["state"] == "awaiting_clarification"
    assert resumed["interaction"]["route"] == "task"
    assert resumed["workflow_ran"] is True
    run.assert_called_once_with(
        "幫我處理一下\n使用者補充：目前這個 repo，直接檢查測試",
        workspace=str(bridge.workspace),
    )


def test_explicit_backend_optimization_starts_an_isolated_background_proposal():
    bridge = _bridge()
    proposal = {
        "id": "sip-0123456789ab",
        "status": "preparing",
        "model": "qwen2.5:7b",
        "changed_files": [],
    }
    bridge.self_improvement.prepare_async = mock.Mock(return_value=proposal)
    try:
        result = bridge.send_message(
            "優化後端的對話路由並補測試",
            session_id="self-improve",
            model_key="open_source",
        )
    finally:
        bridge.stop_background_monitor()

    bridge.self_improvement.prepare_async.assert_called_once_with(
        "優化後端的對話路由並補測試", session_id="self-improve"
    )
    assert result["self_improvement"]["status"] == "preparing"
    assert result["completion"]["state"] == "in_progress"
    assert result["interaction"]["requires_confirmation"] is False
    assert "查看修補 sip-0123456789ab" in result["quick_replies"]


def test_unknown_proposal_does_not_claim_that_isolated_content_exists():
    bridge = _bridge()
    try:
        result = bridge.send_message(
            "查看修補 sip-ffffffffffff",
            session_id="missing-proposal",
        )
    finally:
        bridge.stop_background_monitor()

    assert "找不到指定的修補候選" in result["reply"]
    assert "隔離內容仍保留" not in result["reply"]
    assert result["quick_replies"] == []

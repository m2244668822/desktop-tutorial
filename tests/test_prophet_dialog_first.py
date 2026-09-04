from desktop_chat_app import DesktopBridge


def test_prophet_role_stays_in_dialog_for_explanation_turns():
    bridge = DesktopBridge()
    try:
        assert not bridge._maybe_build_prophet_engineer_handoff(
            message="以圖為例，為什麼申言者每次對話都直接變成任務？",
            role="申言者",
            analysis={"primary_topic": "申言者對談模式"},
            keywords=["申言者", "對談"],
            retrieval_brief="",
        )
        assert not bridge._should_run_workflow(
            message="我想先了解 git 跟 n8n 連線問題，不要直接執行。",
            role="申言者",
            purpose="discussion",
            interaction_mode="auto",
        )
    finally:
        bridge.stop_background_monitor()


def test_prophet_role_handoff_requires_confirmation():
    bridge = DesktopBridge()
    try:
        handoff = bridge._maybe_build_prophet_engineer_handoff(
            message="我確認，請轉成工程師任務並交給工程師處理。",
            role="申言者",
            analysis={"primary_topic": "申言者工程交接"},
            keywords=["申言者", "工程師"],
            retrieval_brief="",
        )
        assert handoff
        assert handoff["mode"] == "prophet_engineer_bridge"
    finally:
        bridge.stop_background_monitor()


def test_prophet_dialog_quality_reply_does_not_emit_tool_report():
    bridge = DesktopBridge()
    try:
        bridge._should_attempt_live_llm_backend = lambda _backend: True
        bridge._generate_live_llm_reply = lambda **_kwargs: (
            "我先跟你對齊：一般對話不該直接被翻成任務；你明確要我動手時，我才切到執行。",
            {"ok": True, "attempted": True, "provider": "nvidia"},
        )
        result = bridge.send_message(
            message="以圖為例，每次對話都是直接任務，應該要先進行對話再確認後轉譯。",
            role="申言者",
            session_id="test-prophet-dialog-first",
            model_key="auto",
            interaction_mode="auto",
        )
        reply = result["reply"]
        assert not result["workflow_ran"]
        assert not result["prophet_engineer_handoff"]
        assert "[申言者->工程師交接]" not in reply
        assert "工具結果" not in reply
        assert "一般對話不該直接被翻成任務" in reply
        assert result["llm_live"]["attempted"]
        assert result["interaction"]["route"] == "conversation"
    finally:
        bridge.stop_background_monitor()


def test_prophet_contextual_miss_question_uses_local_diagnosis_not_cloud_generic_reply():
    bridge = DesktopBridge()
    try:
        bridge._should_attempt_live_llm_backend = lambda _backend: True
        bridge._generate_live_llm_reply = lambda **_kwargs: (
            "核心問題是路由層過早下結論；先保留對話上下文，再由單一閘門決定是否執行。",
            {"ok": True, "attempted": True, "provider": "groq"},
        )
        result = bridge.send_message(
            message="分析智能體對話鬼打牆沒辦法精準抓到我的需求服務的問題，例如目前未找到直接命中，分析前後文內容給出更好的解法。",
            role="申言者",
            session_id="test-prophet-contextual-miss-dialog",
            model_key="groq",
            interaction_mode="auto",
        )
        reply = result["reply"]
        assert result["ok"]
        assert not result["workflow_ran"]
        assert result["llm_live"]["attempted"]
        assert "路由層過早下結論" in reply
        assert "單一閘門" in reply
        assert "Elijah" not in reply
        assert "工程師交接" not in reply
    finally:
        bridge.stop_background_monitor()

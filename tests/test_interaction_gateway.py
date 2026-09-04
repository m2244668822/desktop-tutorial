from core.interaction_gateway import InteractionGateway


def test_normal_dialogue_and_reasoning_do_not_start_tools():
    gateway = InteractionGateway()

    for message in (
        "你好",
        "分析我這個想法哪裡跳太快",
        "幫我寫一個 Python 排序函式",
        "創作一首關於雨的詩",
        "解釋如何刪除檔案，但先不要執行",
        "你覺得應該修改前端嗎？",
        "我覺得之後可以重構這個 repo",
    ):
        decision = gateway.decide(message)
        assert decision.route == "conversation"
        assert not decision.should_execute


def test_explicit_scoped_operations_enter_task_route():
    gateway = InteractionGateway()

    for message in (
        "檢查目前 repo 的測試狀態",
        "修改 templates/chat_shell.html",
        "本機安裝 qwen2.5:7b",
        "提交 Git",
    ):
        decision = gateway.decide(message)
        assert decision.route == "task"
        assert decision.should_execute
        assert not decision.requires_confirmation


def test_ambiguous_operation_asks_which_layer_is_missing():
    decision = InteractionGateway().decide("幫我處理一下")

    assert decision.route == "clarification"
    assert not decision.should_execute
    assert decision.clarification
    assert "目標" in decision.clarification or "範圍" in decision.clarification


def test_high_risk_or_external_side_effect_requires_confirmation():
    gateway = InteractionGateway()

    for message in (
        "刪除舊資料",
        "關閉 Smart App Control",
        "把目前分支 push 到遠端",
        "部署並公開網站",
    ):
        decision = gateway.decide(message)
        assert decision.route == "confirmation"
        assert decision.requires_confirmation
        assert not decision.should_execute


def test_explicit_confirmation_allows_known_high_risk_task():
    decision = InteractionGateway().decide("刪除舊資料", confirmed=True)

    assert decision.route == "task"
    assert decision.should_execute
    assert decision.risk_level == "high"


def test_legacy_frontend_modes_are_hints_not_execution_authority():
    gateway = InteractionGateway()

    for mode in ("analysis", "creative", "coding", "discussion", "qa"):
        decision = gateway.decide("說明依附理論", requested_mode=mode)
        assert decision.route == "conversation"
        assert not decision.should_execute


def test_capability_is_inferred_without_public_mode_switching():
    gateway = InteractionGateway()

    assert gateway.decide("幫我寫一個 Python 函式").capability_mode == "coding"
    assert gateway.decide("比較兩篇研究的證據強度").capability_mode == "research"
    assert gateway.decide("檢查目前 repo 的測試狀態").capability_mode == "coding"


def test_task_route_requires_imperative_or_explicit_request_not_just_keywords():
    gateway = InteractionGateway()

    hypothetical = gateway.decide("我覺得之後可以修改前端")
    imperative = gateway.decide("修改前端的模式選單")

    assert hypothetical.route == "conversation"
    assert not hypothetical.should_execute
    assert imperative.route == "task"
    assert imperative.should_execute

    reversible_ui_edit = gateway.decide("移除前端多餘的模式按鈕")
    assert reversible_ui_edit.route == "task"
    assert not reversible_ui_edit.requires_confirmation


def test_explicit_backend_optimization_routes_to_isolated_self_improvement():
    gateway = InteractionGateway()

    discussion = gateway.decide("你覺得應該如何優化後端？")
    task = gateway.decide("優化後端的對話路由並補測試")

    assert discussion.route == "conversation"
    assert task.route == "task"
    assert task.purpose == "self_improvement"
    assert task.capability_mode == "coding"

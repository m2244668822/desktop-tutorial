from core.prophet_engineer_bridge import (
    build_prophet_engineer_handoff,
    is_prophet_engineer_request,
    render_prophet_engineer_base_reply,
    render_prophet_engineer_reply,
)


def test_prophet_engineer_bridge_is_additive():
    handoff = build_prophet_engineer_handoff(
        message="申言者請把我的想法翻譯成工程語譯給工程師，並做每日最低標準",
        role="申言者",
        analysis={"primary_topic": "每日最低標準"},
        keywords=["申言者", "工程師", "對話回寫"],
    )

    assert handoff["capability_scope"] == "additive_only"
    assert handoff["risk_level"] in {"L0", "L1", "L2", "L3"}
    assert "工程語譯只是額外能力" in handoff["prophet_translation"]
    assert len(handoff["acceptance_criteria"]) >= 4
    assert {"moc", "policy", "report"}.issubset(handoff["doc_links"])


def test_prophet_engineer_request_detection_and_reply_block():
    assert is_prophet_engineer_request("申言者和工程師協作", "總管")
    handoff = build_prophet_engineer_handoff(
        message="請建立神經連結每日最低標準",
        role="申言者",
        analysis={"primary_topic": "神經連結"},
        keywords=["神經連結", "訓練"],
    )
    reply = render_prophet_engineer_reply("【申言者】原本風險判讀保留。", handoff)

    assert "【申言者】原本風險判讀保留。" in reply
    assert "[申言者->工程師交接]" in reply
    assert "必連 MOC" in reply
    assert "必連政策" in reply
    assert "必連報告" in reply


def test_prophet_engineer_base_reply_is_deterministic_and_no_fake_code():
    handoff = build_prophet_engineer_handoff(
        message="申言者把我的想法轉成工程師任務，補強每日最低標準與對話回寫。",
        role="申言者",
        analysis={"primary_topic": "申言者工程語譯"},
        keywords=["申言者", "工程師", "對話回寫"],
    )
    reply = render_prophet_engineer_base_reply(handoff)

    assert "固定交接單" in reply
    assert "原本能力保留" in reply
    assert "新增能力" in reply
    assert "example.com" not in reply
    assert "```" not in reply

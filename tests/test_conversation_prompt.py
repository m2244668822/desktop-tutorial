from core.conversation_prompt import (
    build_recovery_lesson_prompt,
    build_trevor_system_prompt,
)


def test_prompt_prioritizes_natural_dialogue_without_role_reports():
    prompt = build_trevor_system_prompt("general")

    assert "一般談話不要任務化" in prompt
    assert "不輸出角色標籤" in prompt
    assert "不診斷、不奪權" in prompt
    assert "複雜回答最後要看得出結構" in prompt


def test_safety_observation_is_context_not_a_diagnosis():
    prompt = build_trevor_system_prompt(
        "general", safety_nudge="先把這當成感受，不急著判定為事實。"
    )

    assert "本輪安全觀察" in prompt
    assert "不要把它說成診斷" in prompt


def test_capability_modes_keep_their_existing_guidance():
    assert "以一般對談能力回應。" in build_trevor_system_prompt("general")
    assert "正確、可驗證的實作" in build_trevor_system_prompt("coding")
    assert "區分事實、推論與未知" in build_trevor_system_prompt("research")


def test_lesson_prompt_requires_one_question_and_no_diagnosis():
    prompt = build_recovery_lesson_prompt("event", {"event": "和家人爭執"})

    assert "不診斷" in prompt
    assert "不把感受直接判定為外部事實" in prompt
    assert "每輪最多提出一個問題" in prompt
    assert "事件：和家人爭執" in prompt


def test_lesson_prompt_does_not_confirm_unverified_inner_voice():
    prompt = build_recovery_lesson_prompt(
        "inner_content", {"inner_content": "有人命令我離開"}
    )

    assert "不把感受直接判定為外部事實" in prompt
    assert "不得把內在聲音當成權威指示或外部訊息" in prompt
    assert "內在語句／聲音／想法：有人命令我離開" in prompt


def test_faith_terms_absent_without_opt_in():
    prompt = build_recovery_lesson_prompt("event", {})

    for term in ("聖經", "神", "贖罪", "寬恕"):
        assert term not in prompt


def test_faith_terms_are_optional_and_non_authoritative_when_opted_in():
    prompt = build_recovery_lesson_prompt("event", {}, faith_opt_in=True)

    assert "可選的意義整理框架" in prompt
    assert "聖經" in prompt
    assert "不具權威" in prompt
    assert "可以拒絕、退出或設下界線" in prompt


def test_safety_hold_prompt_cannot_continue_lesson():
    prompt = build_recovery_lesson_prompt("event", {}, safety_hold=True)

    assert "先確認你現在是否安全" in prompt
    assert "不要繼續課程" in prompt
    assert "不要要求填寫下一格" in prompt

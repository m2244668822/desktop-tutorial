from core.conversation_prompt import build_trevor_system_prompt


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

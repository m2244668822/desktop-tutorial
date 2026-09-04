from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT = (ROOT / "templates" / "chat_shell.html").read_text(encoding="utf-8")
SERVER = (ROOT / "core" / "web_server.py").read_text(encoding="utf-8")


def test_primary_chat_surface_has_one_input_without_public_cognitive_modes():
    assert 'id="msgInput"' in CHAT
    assert 'id="sendBtn"' in CHAT
    assert "📝 一般對話" not in CHAT
    assert "🔍 深度分析" not in CHAT
    assert "💻 程式生成" not in CHAT
    assert "🎨 創意寫作" not in CHAT


def test_optional_overrides_are_inside_advanced_settings():
    advanced_start = CHAT.index('id="advancedPanel"')
    input_start = CHAT.index('class="input-bar"', advanced_start)
    advanced = CHAT[advanced_start:input_start]

    assert 'id="interactionSelect"' in advanced
    assert '<option value="auto">自動判斷</option>' in advanced
    assert '<option value="conversation">只對話，不執行</option>' in advanced
    assert '<option value="task">指定為任務</option>' in advanced
    assert 'id="capabilitySelect"' in advanced
    assert 'id="deliberationSelect"' in advanced


def test_chat_has_no_frontend_permission_bypass():
    for forbidden in (
        "lowRestrict",
        "permission_bypass",
        "X-Agent-Internal",
        "agent-internal-bypass",
        "最低權限 ON",
    ):
        assert forbidden not in CHAT


def test_normal_message_send_is_one_step():
    assert "SEND_CONFIRM_WINDOW_MS" not in CHAT
    assert "armSendConfirmation" not in CHAT
    assert "再按一次送出" not in CHAT
    assert "return sendMessage();" in CHAT
    assert "Enter 送出" in CHAT


def test_legacy_web_pages_redirect_to_the_canonical_chat_shell():
    for route in (
        '"/chat": "/chat_shell"',
        '"/agent_shell": "/chat_shell"',
        '"/monitor_shell": "/chat_shell"',
    ):
        assert route in SERVER


def test_model_switch_notice_is_not_sent_as_conversation_history():
    assert "{ contextTransient: true }" in CHAT
    assert 'el.dataset.contextTransient === "true"' in CHAT

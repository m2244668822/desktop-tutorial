from desktop_chat_app import DesktopBridge


def test_all_visible_agents_report_memory_and_aeg_capabilities():
    bridge = DesktopBridge(energy_lite=True)
    try:
        status = bridge.get_agent_memory_aeg_status()
        roles = {item["role"] for item in status["roles"]}
        assert {"總管", "研究員", "工程師", "小編", "申言者"}.issubset(roles)
        assert status["capability_model"] == "shared_layer_per_role"
        assert status["aeg"]["keywords_count"] >= 1
        assert status["knowledge_hub"]["total_items"] >= 1
        for item in status["roles"]:
            assert item["long_term_memory"] is True
            assert item["knowledge_search"] is True
            assert item["aeg_search"] is True
    finally:
        bridge.stop_background_monitor()


def test_diag_endpoint_includes_agent_memory_aeg_contract():
    text = open("core/web_server.py", encoding="utf-8").read()
    assert '"agent_memory_aeg": server_instance.bridge.get_agent_memory_aeg_status()' in text
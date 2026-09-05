from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = (ROOT / "tools" / "n8n_watchdog_windows.ps1").read_text(encoding="utf-8-sig")
STARTER = (ROOT / "tools" / "start_n8n_windows.ps1").read_text(encoding="utf-8-sig")


def test_windows_n8n_scripts_resolve_winget_user_install():
    for script in (WATCHDOG, STARTER):
        assert "function Resolve-N8nCommand" in script
        assert "OpenJS.NodeJS.LTS*" in script
        assert 'Filter "n8n.cmd"' in script


def test_windows_n8n_scripts_use_low_traffic_security_defaults():
    for script in (WATCHDOG, STARTER):
        assert "N8N_DIAGNOSTICS_ENABLED=false" in script
        assert "N8N_DISABLED_MODULES=mcp-registry" in script
        assert "N8N_UNVERIFIED_PACKAGES_ENABLED=false" in script
        assert "N8N_COMPRESSION_NODE_MAX_DECOMPRESSED_SIZE_BYTES=268435456" in script
        assert "N8N_COMPRESSION_NODE_MAX_ZIP_ENTRIES=1000" in script

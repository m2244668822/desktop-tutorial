from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOKS = [
    ROOT / "docs" / "dev" / "FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md",
    ROOT / "docs" / "dev" / "MAC_GIT_HANDOFF_PACKAGE_2026-06-29.md",
    ROOT / "docs" / "dev" / "RUNTIME_BROWSER_SMOKE_EVIDENCE_2026-07-04.md",
    ROOT / "docs" / "dev" / "SHELL_WORKSPACE_PATH_TROUBLESHOOTING_2026-07-04.md",
    ROOT / "docs" / "dev" / "STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27.md",
]


def private_use_codepoints(text: str) -> list[str]:
    return [
        char
        for char in text
        if 0xE000 <= ord(char) <= 0xF8FF
    ]


def test_core_runbooks_stay_utf8_clean():
    for path in RUNBOOKS:
        text = path.read_text(encoding="utf-8")

        assert "\ufffd" not in text, path
        assert not private_use_codepoints(text), path


def test_shell_workspace_runbook_records_current_paths():
    text = (ROOT / "docs" / "dev" / "SHELL_WORKSPACE_PATH_TROUBLESHOOTING_2026-07-04.md").read_text(
        encoding="utf-8"
    )
    windows_repo = "E:\\\u667a\u80fd\u9ad4\\\u57ce\u57ce\u57ce\u7a0b\u5f0f"
    stale_windows_repo = "F:\\\u57ce\u57ce\u57ce\u7a0b\u5f0f"

    assert windows_repo in text
    assert stale_windows_repo in text
    assert "/Volumes/<volume>/<clone>" in text

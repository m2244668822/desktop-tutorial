import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from core.self_improvement import SelfImprovementService


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _repository(parent: Path) -> Path:
    root = parent / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "Trevor Test")
    _git(root, "config", "user.email", "trevor@example.invalid")
    (root / "core").mkdir()
    (root / "tests").mkdir()
    (root / "core" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "initial")
    return root


def _service(root: Path, data: Path, runner) -> SelfImprovementService:
    return SelfImprovementService(
        root,
        data,
        codex_path=sys.executable,
        runner=runner,
        validation_commands=(),
    )


def test_control_commands_require_explicit_proposal_id():
    proposal = "sip-0123456789ab"

    assert SelfImprovementService.parse_control_command(f"確認套用 {proposal}") == (
        "apply",
        proposal,
    )
    assert SelfImprovementService.parse_control_command(f"查看修補 {proposal}") == (
        "status",
        proposal,
    )
    assert SelfImprovementService.parse_control_command("確認套用") is None


def test_prepare_keeps_patch_isolated_until_same_session_applies_it():
    captured_command = []

    def runner(_command, **kwargs):
        captured_command.extend(_command)
        worktree = Path(kwargs["cwd"])
        (worktree / "core" / "sample.py").write_text("VALUE = 2\n", encoding="utf-8")
        return subprocess.CompletedProcess(_command, 0, stdout="done", stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        root = _repository(parent)
        service = _service(root, parent / "data", runner)

        proposal = service.prepare(
            "優化後端 sample 的數值處理並保持行為可測試",
            session_id="chat-a",
        )

        assert proposal["status"] == "ready_for_approval"
        assert "--ask-for-approval" not in captured_command
        assert 'approval_policy="never"' in captured_command
        assert proposal["changed_files"] == ["core/sample.py"]
        assert (root / "core" / "sample.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        with pytest.raises(RuntimeError, match="proposal_session_mismatch"):
            service.apply(proposal["id"], session_id="chat-b")

        applied = service.apply(proposal["id"], session_id="chat-a")

        assert applied["status"] == "applied"
        assert applied["applied_commit"]
        assert (root / "core" / "sample.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_async_prepare_returns_before_the_coding_worker_finishes():
    release = threading.Event()

    def runner(_command, **kwargs):
        release.wait(timeout=2)
        worktree = Path(kwargs["cwd"])
        (worktree / "core" / "sample.py").write_text("VALUE = 3\n", encoding="utf-8")
        return subprocess.CompletedProcess(_command, 0, stdout="done", stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        root = _repository(parent)
        service = _service(root, parent / "data", runner)

        proposal = service.prepare_async(
            "優化後端 sample 的數值處理並在背景執行",
            session_id="chat-a",
        )

        assert proposal["status"] == "preparing"
        worker = service._workers[proposal["id"]]
        release.set()
        worker.join(timeout=5)
        ready = service.public_get_for_session(proposal["id"], session_id="chat-a")
        assert ready["status"] == "ready_for_approval"
        assert (root / "core" / "sample.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_rejecting_a_running_proposal_prevents_it_from_becoming_ready():
    release = threading.Event()

    def runner(_command, **kwargs):
        release.wait(timeout=2)
        worktree = Path(kwargs["cwd"])
        (worktree / "core" / "sample.py").write_text("VALUE = 4\n", encoding="utf-8")
        return subprocess.CompletedProcess(_command, 0, stdout="done", stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        root = _repository(parent)
        service = _service(root, parent / "data", runner)
        proposal = service.prepare_async(
            "優化後端 sample 並驗證取消中的競態行為",
            session_id="chat-a",
        )
        worker = service._workers[proposal["id"]]

        rejected = service.reject(proposal["id"], session_id="chat-a")
        release.set()
        worker.join(timeout=5)

        final = service.public_get_for_session(proposal["id"], session_id="chat-a")
        assert rejected["status"] == "rejected"
        assert final["status"] == "rejected"
        assert (root / "core" / "sample.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_scope_violation_never_changes_running_checkout():
    def runner(_command, **kwargs):
        worktree = Path(kwargs["cwd"])
        (worktree / "templates").mkdir()
        (worktree / "templates" / "chat.html").write_text("unsafe\n", encoding="utf-8")
        return subprocess.CompletedProcess(_command, 0, stdout="done", stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        root = _repository(parent)
        service = _service(root, parent / "data", runner)

        proposal = service.prepare(
            "優化後端但錯誤地動到前端模板以測試邊界",
            session_id="chat-a",
        )

        assert proposal["status"] == "failed"
        assert proposal["validation"]["reason"] == "scope_violation"
        assert not (root / "templates" / "chat.html").exists()


def test_existing_tests_and_security_files_are_protected():
    service = SelfImprovementService(".", ".", codex_path=sys.executable)

    assert service._validate_changed_path("tests/test_existing.py") == "existing_tests_are_protected"
    assert service._validate_changed_path("core/api_auth.py") == "protected_security_file"
    assert service._validate_changed_path("templates/chat_shell.html") == "outside_backend_scope"
    assert service._validate_changed_path("core/router.py") == ""

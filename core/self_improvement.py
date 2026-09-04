"""Controlled backend self-improvement proposals for Trevor.

The coding model may edit and validate an isolated Git worktree.  It cannot
merge the result into the running branch; applying a ready proposal requires
an explicit proposal id and a clean, unchanged base checkout.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Sequence

from core.secret_scanner import SecretScanner


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SelfImprovementService:
    """Prepare, validate and explicitly apply isolated backend patches."""

    _ID = re.compile(r"^sip-[a-f0-9]{12}$")
    _APPLY = re.compile(r"^確認套用\s+(sip-[a-f0-9]{12})$", re.IGNORECASE)
    _STATUS = re.compile(r"^(?:修補狀態|查看修補)\s+(sip-[a-f0-9]{12})$", re.IGNORECASE)
    _REJECT = re.compile(r"^(?:取消修補|拒絕修補)\s+(sip-[a-f0-9]{12})$", re.IGNORECASE)
    _ALLOWED_PREFIXES = ("core/", "tools/", "tests/")
    _ALLOWED_ROOT_FILES = frozenset({"desktop_chat_app.py", "system_main.py"})
    _PROTECTED_PARTS = frozenset(
        {
            ".git",
            ".github",
            ".venv",
            "config",
            "data",
            "deploy",
            "logs",
            "secrets",
        }
    )
    _PROTECTED_NAME_MARKERS = (
        "api_auth",
        "credential",
        "keychain",
        "secret",
        "permission",
    )

    def __init__(
        self,
        repository_root: str | Path,
        data_root: str | Path,
        *,
        codex_path: str | Path | None = None,
        model: str | None = None,
        timeout_seconds: int = 300,
        runner: Runner = subprocess.run,
        validation_commands: Iterable[Sequence[str]] | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.root = self.data_root / "self_improvement"
        self.worktrees_root = self.root / "worktrees"
        self.proposals_root = self.root / "proposals"
        configured_codex = str(codex_path or os.getenv("TREVOR_CODEX_PATH", "")).strip()
        self.codex_path = configured_codex or shutil.which("codex") or ""
        self.model = str(model or os.getenv("TREVOR_CODING_MODEL", "qwen2.5:7b")).strip()
        self.timeout_seconds = max(30, min(600, int(timeout_seconds)))
        self.runner = runner
        self.validation_commands = tuple(validation_commands) if validation_commands is not None else (
            (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_interaction_gateway.py",
                "tests/test_trevor_interaction_v2.py",
                "tests/test_trevor_api_contract.py",
                "tests/test_self_improvement.py",
            ),
        )
        self._lock = threading.RLock()
        self._workers: dict[str, threading.Thread] = {}

    @classmethod
    def parse_control_command(cls, message: str) -> tuple[str, str] | None:
        text = str(message or "").strip()
        for action, pattern in (
            ("apply", cls._APPLY),
            ("status", cls._STATUS),
            ("reject", cls._REJECT),
        ):
            match = pattern.fullmatch(text)
            if match:
                return action, match.group(1).lower()
        return None

    def availability(self) -> dict[str, Any]:
        git = shutil.which("git")
        codex = self._resolve_codex_path()
        return {
            "ok": bool(git and codex and self.repository_root.joinpath(".git").exists()),
            "git_available": bool(git),
            "codex_available": bool(codex),
            "model": self.model,
            "mode": "isolated_proposal",
            "auto_merge": False,
        }

    def _resolve_codex_path(self) -> str:
        configured = str(self.codex_path or "").strip()
        if not configured:
            return ""
        candidate = Path(configured)
        if candidate.is_absolute() or candidate.parent != Path("."):
            return configured if candidate.is_file() else ""
        return shutil.which(configured) or ""

    def _git(
        self,
        *arguments: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repository_root,
            check=check,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _proposal_path(self, proposal_id: str) -> Path:
        proposal = str(proposal_id or "").strip().lower()
        if not self._ID.fullmatch(proposal):
            raise ValueError("invalid_proposal_id")
        return self.proposals_root / f"{proposal}.json"

    def _save(self, state: dict[str, Any]) -> None:
        path = self._proposal_path(str(state.get("id", "")))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def get(self, proposal_id: str) -> dict[str, Any]:
        path = self._proposal_path(proposal_id)
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyError("proposal_not_found") from None
        if not isinstance(state, dict):
            raise RuntimeError("proposal_state_invalid")
        return dict(state)

    def list(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not self.proposals_root.exists():
            return []
        states: list[dict[str, Any]] = []
        for path in sorted(
            self.proposals_root.glob("sip-*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[: max(1, min(100, int(limit)))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                states.append(payload)
        return states

    @staticmethod
    def _public(state: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "id",
            "status",
            "base_branch",
            "base_head",
            "proposal_branch",
            "proposal_commit",
            "applied_commit",
            "model",
            "changed_files",
            "validation",
            "error",
            "created_at",
            "updated_at",
            "applied_at",
        }
        public = {key: state.get(key) for key in allowed if key in state}
        instruction = str(state.get("instruction", "") or "").strip()
        if instruction:
            public["instruction_preview"] = instruction[:240]
        return public

    def public_get(self, proposal_id: str) -> dict[str, Any]:
        return self._public(self.get(proposal_id))

    def public_get_for_session(
        self, proposal_id: str, *, session_id: str = ""
    ) -> dict[str, Any]:
        state = self.get(proposal_id)
        self._check_session(state, session_id)
        return self._public(state)

    def public_list(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [self._public(state) for state in self.list(limit=limit)]

    def _ensure_clean_repository(self) -> tuple[str, str]:
        if not self.availability()["ok"]:
            raise RuntimeError("self_improvement_engine_unavailable")
        branch = self._git("branch", "--show-current").stdout.strip()
        head = self._git("rev-parse", "HEAD").stdout.strip()
        if not branch or not head:
            raise RuntimeError("repository_head_unavailable")
        if self._git("status", "--porcelain").stdout.strip():
            raise RuntimeError("repository_dirty")
        return branch, head

    @staticmethod
    def _safe_environment() -> dict[str, str]:
        keep = {
            "ALLUSERSPROFILE",
            "APPDATA",
            "COMSPEC",
            "HOMEDRIVE",
            "HOMEPATH",
            "LOCALAPPDATA",
            "OLLAMA_HOST",
            "PATH",
            "PATHEXT",
            "PROGRAMDATA",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        }
        return {key: value for key, value in os.environ.items() if key.upper() in keep}

    def _codex_prompt(self, instruction: str, proposal_id: str) -> str:
        return (
            "你正在崔佛的隔離 Git worktree 內準備後端修補候選。\n"
            f"提案編號：{proposal_id}\n"
            f"需求：{instruction}\n\n"
            "請先讀取相關程式與既有測試，再做最小且可驗證的修改。"
            "只可修改 core/、tools/、desktop_chat_app.py、system_main.py，"
            f"以及新增 tests/test_trevor_generated_{proposal_id[4:]}.py；"
            "不可修改既有測試、前端、部署、設定、憑證、認證、權限或秘密管理程式。"
            "不可安裝套件、不可使用網路、不可提交 Git、不可合併分支。"
            "若需求不夠具體或無法安全完成，請不要修改檔案，直接說明缺少資訊。"
        )

    def _invoke_codex(self, worktree: Path, instruction: str, proposal_id: str) -> dict[str, Any]:
        command = [
            self._resolve_codex_path(),
            "exec",
            "--oss",
            "--local-provider",
            "ollama",
            "--model",
            self.model,
            "--sandbox",
            "workspace-write",
            "--config",
            'approval_policy="never"',
            "--ephemeral",
            "--ignore-user-config",
            "--color",
            "never",
            "--cd",
            str(worktree),
            "-",
        ]
        try:
            result = self.runner(
                command,
                cwd=worktree,
                input=self._codex_prompt(instruction, proposal_id),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                env=self._safe_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("coding_engine_timeout") from exc
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "summary": (result.stdout or result.stderr or "")[-4000:],
        }

    def _changed_files(self, worktree: Path) -> list[str]:
        tracked = self._git("diff", "--name-only", "HEAD", cwd=worktree).stdout.splitlines()
        untracked = self._git(
            "ls-files", "--others", "--exclude-standard", cwd=worktree
        ).stdout.splitlines()
        return sorted({item.replace("\\", "/").strip() for item in (*tracked, *untracked) if item.strip()})

    def _validate_changed_path(self, relative: str) -> str:
        normalized = PurePosixPath(relative)
        if normalized.is_absolute() or ".." in normalized.parts:
            return "path_escape"
        lowered = relative.lower()
        if any(part.lower() in self._PROTECTED_PARTS for part in normalized.parts):
            return "protected_path"
        if any(marker in lowered for marker in self._PROTECTED_NAME_MARKERS):
            return "protected_security_file"
        allowed = relative in self._ALLOWED_ROOT_FILES or relative.startswith(self._ALLOWED_PREFIXES)
        if not allowed:
            return "outside_backend_scope"
        if relative.startswith("tests/"):
            generated = re.fullmatch(r"tests/test_trevor_generated_[a-f0-9]{12}\.py", relative)
            if not generated:
                return "existing_tests_are_protected"
        return ""

    def _validate(self, worktree: Path, changed_files: list[str]) -> dict[str, Any]:
        if not changed_files:
            return {"ok": False, "reason": "no_code_changes"}
        findings = [
            {"path": path, "reason": reason}
            for path in changed_files
            if (reason := self._validate_changed_path(path))
        ]
        if findings:
            return {"ok": False, "reason": "scope_violation", "findings": findings}
        diff_check = self._git("diff", "--check", "HEAD", cwd=worktree, check=False)
        if diff_check.returncode:
            return {"ok": False, "reason": "diff_check_failed"}
        scan = SecretScanner(worktree).scan_paths(worktree / path for path in changed_files)
        if not scan.get("ok"):
            return {
                "ok": False,
                "reason": "secret_scan_failed",
                "findings": scan.get("findings", []),
            }
        checks: list[dict[str, Any]] = []
        python_files = [str(worktree / path) for path in changed_files if path.endswith(".py")]
        if python_files:
            compile_result = subprocess.run(
                [sys.executable, "-m", "py_compile", *python_files],
                cwd=worktree,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            checks.append(
                {"command": [sys.executable, "-m", "py_compile", "<changed-python-files>"], "returncode": compile_result.returncode}
            )
            if compile_result.returncode:
                return {"ok": False, "reason": "compile_failed", "checks": checks}
        for command in self.validation_commands:
            result = subprocess.run(
                list(command),
                cwd=worktree,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            checks.append({"command": list(command), "returncode": result.returncode})
            if result.returncode:
                return {"ok": False, "reason": "tests_failed", "checks": checks}
        return {
            "ok": True,
            "reason": "validated",
            "checks": checks,
            "secret_scan": {"scanned_files": scan.get("scanned_files", 0)},
        }

    def _begin_preparation(
        self, instruction: str, *, session_id: str = ""
    ) -> tuple[dict[str, Any], Path, str]:
        request = str(instruction or "").strip()
        if len(request) < 12:
            raise ValueError("self_improvement_instruction_too_short")
        branch, head = self._ensure_clean_repository()
        proposal_id = f"sip-{uuid.uuid4().hex[:12]}"
        proposal_branch = f"trevor/proposal/{proposal_id}"
        worktree = (self.worktrees_root / proposal_id).resolve()
        if not worktree.is_relative_to(self.worktrees_root.resolve()):
            raise RuntimeError("worktree_path_escape")
        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {
            "id": proposal_id,
            "status": "preparing",
            "instruction": request[:4000],
            "session_id": str(session_id or "default")[:128],
            "base_branch": branch,
            "base_head": head,
            "proposal_branch": proposal_branch,
            "worktree": str(worktree),
            "model": self.model,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self._git("worktree", "add", "-b", proposal_branch, str(worktree), head)
        self._save(state)
        return state, worktree, request

    def _finish_preparation(
        self, state: dict[str, Any], worktree: Path, request: str
    ) -> dict[str, Any]:
        proposal_id = str(state["id"])
        try:
            engine = self._invoke_codex(worktree, request, proposal_id)
            state["engine"] = engine
            if not engine["ok"]:
                raise RuntimeError("coding_engine_failed")
            if self.get(proposal_id).get("status") == "rejected":
                raise RuntimeError("proposal_rejected")
            changed_files = self._changed_files(worktree)
            state["changed_files"] = changed_files
            validation = self._validate(worktree, changed_files)
            state["validation"] = validation
            if not validation.get("ok"):
                raise RuntimeError(str(validation.get("reason", "validation_failed")))
            if self.get(proposal_id).get("status") == "rejected":
                raise RuntimeError("proposal_rejected")
            self._git("add", "--all", cwd=worktree)
            self._git(
                "-c",
                "user.name=Trevor Self-Improvement",
                "-c",
                "user.email=trevor@local.invalid",
                "commit",
                "-m",
                f"trevor proposal: {proposal_id}",
                cwd=worktree,
            )
            state["proposal_commit"] = self._git(
                "rev-parse", "HEAD", cwd=worktree
            ).stdout.strip()
            state["status"] = "ready_for_approval"
            state["error"] = ""
        except Exception as exc:
            current = self.get(proposal_id)
            if current.get("status") == "rejected":
                state = current
            else:
                state["status"] = "failed"
                state["error"] = str(exc)[:500]
        with self._lock:
            state["updated_at"] = _now_iso()
            self._save(state)
            self._workers.pop(proposal_id, None)
        return self._public(state)

    def prepare(self, instruction: str, *, session_id: str = "") -> dict[str, Any]:
        with self._lock:
            state, worktree, request = self._begin_preparation(
                instruction, session_id=session_id
            )
        return self._finish_preparation(state, worktree, request)

    def prepare_async(self, instruction: str, *, session_id: str = "") -> dict[str, Any]:
        with self._lock:
            state, worktree, request = self._begin_preparation(
                instruction, session_id=session_id
            )
            proposal_id = str(state["id"])
            worker = threading.Thread(
                target=self._finish_preparation,
                args=(state, worktree, request),
                name=f"trevor-{proposal_id}",
                daemon=True,
            )
            self._workers[proposal_id] = worker
            worker.start()
        return self._public(state)

    @staticmethod
    def _check_session(state: dict[str, Any], session_id: str) -> None:
        expected = str(state.get("session_id", "default") or "default")
        actual = str(session_id or "default")[:128]
        if expected != actual:
            raise RuntimeError("proposal_session_mismatch")

    def apply(self, proposal_id: str, *, session_id: str = "") -> dict[str, Any]:
        with self._lock:
            state = self.get(proposal_id)
            self._check_session(state, session_id)
            if state.get("status") != "ready_for_approval":
                raise RuntimeError("proposal_not_ready")
            branch, head = self._ensure_clean_repository()
            if branch != state.get("base_branch") or head != state.get("base_head"):
                raise RuntimeError("proposal_base_changed")
            commit = str(state.get("proposal_commit", "") or "").strip()
            if not commit:
                raise RuntimeError("proposal_commit_missing")
            result = self._git("cherry-pick", commit, check=False)
            if result.returncode:
                self._git("cherry-pick", "--abort", check=False)
                raise RuntimeError("proposal_apply_conflict")
            state["status"] = "applied"
            state["applied_at"] = _now_iso()
            state["updated_at"] = state["applied_at"]
            state["applied_commit"] = self._git("rev-parse", "HEAD").stdout.strip()
            self._save(state)
            return self._public(state)

    def reject(self, proposal_id: str, *, session_id: str = "") -> dict[str, Any]:
        with self._lock:
            state = self.get(proposal_id)
            self._check_session(state, session_id)
            if state.get("status") == "applied":
                raise RuntimeError("applied_proposal_cannot_be_rejected")
            state["status"] = "rejected"
            state["updated_at"] = _now_iso()
            self._save(state)
            return self._public(state)


__all__ = ["SelfImprovementService"]

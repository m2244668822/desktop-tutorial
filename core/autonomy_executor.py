from __future__ import annotations

import inspect
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from core.audit_chain import HashChainAuditLog
from core.autonomy_claim import ClaimCancellation, ClaimLostError
from core.git_worktree import TrevorWorktreeManager
from core.secret_scanner import SecretScanner
from core.workflow_runtime import run_task_plan


Workflow = Callable[..., dict[str, Any]]


class TrevorTaskExecutor:
    CODE_CATEGORIES = frozenset({'bugfix', 'test', 'refactor', 'small_feature'})

    def __init__(
        self,
        repository_root: str | Path,
        data_root: str | Path,
        *,
        workflow: Workflow = run_task_plan,
        test_commands: Iterable[Sequence[str]] | None = None,
        audit_log: HashChainAuditLog | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.workflow = workflow
        self.worktrees = TrevorWorktreeManager(self.repository_root, self.data_root)
        self.test_commands = tuple(test_commands) if test_commands is not None else (
            (sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'),
        )
        self.audit_log = audit_log

    def _audit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.audit_log is not None:
            self.audit_log.append(event_type, payload)

    @staticmethod
    def _workflow_summary(result: dict[str, Any]) -> dict[str, Any]:
        state = result.get('task_state', {}) if isinstance(result, dict) else {}
        return {
            'task_id': str(state.get('task_id', '') or ''),
            'overall_status': str(state.get('overall_status', 'failed') or 'failed'),
            'completed_steps': int(state.get('completed_steps', 0) or 0),
            'failed_steps': int(state.get('failed_steps', 0) or 0),
        }

    @staticmethod
    def _check_claim(cancellation: ClaimCancellation | None) -> None:
        if cancellation is not None:
            cancellation.raise_if_lost()

    @staticmethod
    def _run_validation_command(
        command: Sequence[str],
        worktree_path: Path,
        cancellation: ClaimCancellation | None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = list(command)
        if cancellation is None:
            return subprocess.run(
                arguments,
                cwd=worktree_path,
                check=False,
                capture_output=True,
                text=True,
            )
        popen_options: dict[str, Any] = {}
        if os.name == 'posix':
            popen_options['start_new_session'] = True
        elif hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
            popen_options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            arguments,
            cwd=worktree_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen_options,
        )
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                return subprocess.CompletedProcess(
                    arguments,
                    process.returncode,
                    stdout,
                    stderr,
                )
            except subprocess.TimeoutExpired:
                if not cancellation.is_lost():
                    continue
                TrevorTaskExecutor._terminate_process_tree(process)
                cancellation.raise_if_lost()

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if os.name == 'posix':
            process_group = process.pid
            group_survived = True
            try:
                os.killpg(process_group, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                group_survived = False
            deadline = time.monotonic() + 0.25
            while group_survived and time.monotonic() < deadline:
                try:
                    os.killpg(process_group, 0)
                except (ProcessLookupError, PermissionError):
                    group_survived = False
                    break
                time.sleep(0.02)
            if group_survived:
                try:
                    os.killpg(process_group, 0)
                except (ProcessLookupError, PermissionError):
                    group_survived = False
            if group_survived:
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        elif os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(process.pid), '/T', '/F'],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            if process.poll() is None:
                process.terminate()
        try:
            process.communicate(timeout=2)
            return
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=2)

    def _run_workflow(
        self,
        workspace: Path,
        task: dict[str, Any],
        cancellation: ClaimCancellation | None,
    ) -> dict[str, Any]:
        self._check_claim(cancellation)
        arguments = (
            workspace,
            str(task.get('capability_mode', 'general') or 'general'),
            str(task.get('input', '') or ''),
        )
        try:
            parameters = inspect.signature(self.workflow).parameters.values()
            supports_cancel_check = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                or (
                    parameter.name == 'cancel_check'
                    and parameter.kind
                    in {
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    }
                )
                for parameter in parameters
            )
        except (TypeError, ValueError):
            supports_cancel_check = False
        result = (
            self.workflow(
                *arguments,
                cancel_check=(
                    cancellation.raise_if_lost if cancellation is not None else None
                ),
            )
            if supports_cancel_check
            else self.workflow(*arguments)
        )
        self._check_claim(cancellation)
        summary = self._workflow_summary(result)
        if summary['overall_status'].lower() != 'success' or summary['failed_steps']:
            raise RuntimeError('workflow_failed')
        return summary

    def _validate(
        self,
        worktree_path: Path,
        cancellation: ClaimCancellation | None,
    ) -> dict[str, Any]:
        self._check_claim(cancellation)
        scan = SecretScanner(worktree_path).scan_repository()
        self._check_claim(cancellation)
        if not scan['ok']:
            return {'ok': False, 'reason': 'secret_scan_failed', 'findings': scan['findings']}
        checks = []
        for command in self.test_commands:
            self._check_claim(cancellation)
            process = self._run_validation_command(
                command,
                worktree_path,
                cancellation,
            )
            self._check_claim(cancellation)
            checks.append({'command': list(command), 'returncode': process.returncode})
            if process.returncode != 0:
                return {'ok': False, 'reason': 'tests_failed', 'checks': checks}
        return {'ok': True, 'checks': checks, 'secret_scan': {'scanned_files': scan['scanned_files']}}

    def _execute_code_task(
        self,
        task: dict[str, Any],
        cancellation: ClaimCancellation | None,
    ) -> dict[str, Any]:
        self._check_claim(cancellation)
        claim_attempt_id = str(task.get('claim_attempt_id', '') or '').strip()
        if not claim_attempt_id:
            claim_attempt_id = uuid.uuid4().hex
        worktree_task_id = (
            f"{claim_attempt_id}-{str(task.get('id', '') or 'task')}"
        )
        created = self.worktrees.create(
            worktree_task_id,
            str(task.get('input', '') or 'task'),
            cancel_check=(
                cancellation.raise_if_lost if cancellation is not None else None
            ),
        )
        worktree_path = Path(created['path'])
        try:
            self._check_claim(cancellation)
            self._audit(
                'autonomy_worktree_created',
                {'task_id': task.get('id', ''), 'branch': created['branch']},
            )
            workflow = self._run_workflow(worktree_path, task, cancellation)
            self._check_claim(cancellation)
            git_result = self.worktrees.finalize(
                created,
                commit_message=f"trevor: task {str(task.get('id', '') or 'unknown')[:80]}",
                validator=lambda path: self._validate(path, cancellation),
                cancel_check=(
                    cancellation.raise_if_lost if cancellation is not None else None
                ),
            )
        except ClaimLostError:
            try:
                self.worktrees.discard(created)
            except Exception:
                pass
            raise
        self._audit(
            'autonomy_task_merged',
            {'task_id': task.get('id', ''), 'git': git_result, 'workflow': workflow},
        )
        return {'status': 'completed', 'workflow': workflow, 'git': git_result}

    def _execute_non_code_task(
        self,
        task: dict[str, Any],
        cancellation: ClaimCancellation | None,
    ) -> dict[str, Any]:
        self._check_claim(cancellation)
        before = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self._check_claim(cancellation)
        workflow = self._run_workflow(self.repository_root, task, cancellation)
        self._check_claim(cancellation)
        after = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self._check_claim(cancellation)
        if after != before:
            raise RuntimeError('non_code_task_modified_repository')
        self._audit(
            'autonomy_task_completed',
            {'task_id': task.get('id', ''), 'workflow': workflow},
        )
        return {'status': 'completed', 'workflow': workflow, 'git': {'status': 'not_required'}}

    def __call__(
        self,
        task: dict[str, Any],
        *,
        cancellation: ClaimCancellation | None = None,
        before_publish: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        self._check_claim(cancellation)
        if before_publish is not None:
            before_publish()
        self._check_claim(cancellation)
        category = str(task.get('category', 'maintenance') or 'maintenance').lower()
        self._audit(
            'autonomy_task_started',
            {'task_id': task.get('id', ''), 'category': category},
        )
        self._check_claim(cancellation)
        if category in self.CODE_CATEGORIES:
            return self._execute_code_task(task, cancellation)
        return self._execute_non_code_task(task, cancellation)


__all__ = ['TrevorTaskExecutor']

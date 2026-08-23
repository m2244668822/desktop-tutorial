from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from core.audit_chain import HashChainAuditLog
from core.git_worktree import TrevorWorktreeManager
from core.secret_scanner import SecretScanner
from core.workflow_runtime import run_task_plan


Workflow = Callable[[str | Path, str, str], dict[str, Any]]


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

    def _run_workflow(self, workspace: Path, task: dict[str, Any]) -> dict[str, Any]:
        result = self.workflow(
            workspace,
            str(task.get('capability_mode', 'general') or 'general'),
            str(task.get('input', '') or ''),
        )
        summary = self._workflow_summary(result)
        if summary['overall_status'].lower() != 'success' or summary['failed_steps']:
            raise RuntimeError('workflow_failed')
        return summary

    def _validate(self, worktree_path: Path) -> dict[str, Any]:
        scan = SecretScanner(worktree_path).scan_repository()
        if not scan['ok']:
            return {'ok': False, 'reason': 'secret_scan_failed', 'findings': scan['findings']}
        checks = []
        for command in self.test_commands:
            process = subprocess.run(
                list(command),
                cwd=worktree_path,
                check=False,
                capture_output=True,
                text=True,
            )
            checks.append({'command': list(command), 'returncode': process.returncode})
            if process.returncode != 0:
                return {'ok': False, 'reason': 'tests_failed', 'checks': checks}
        return {'ok': True, 'checks': checks, 'secret_scan': {'scanned_files': scan['scanned_files']}}

    def _execute_code_task(self, task: dict[str, Any]) -> dict[str, Any]:
        created = self.worktrees.create(
            str(task.get('id', '') or 'task'),
            str(task.get('input', '') or 'task'),
        )
        worktree_path = Path(created['path'])
        self._audit(
            'autonomy_worktree_created',
            {'task_id': task.get('id', ''), 'branch': created['branch']},
        )
        workflow = self._run_workflow(worktree_path, task)
        git_result = self.worktrees.finalize(
            created,
            commit_message=f"trevor: task {str(task.get('id', '') or 'unknown')[:80]}",
            validator=self._validate,
        )
        self._audit(
            'autonomy_task_merged',
            {'task_id': task.get('id', ''), 'git': git_result, 'workflow': workflow},
        )
        return {'status': 'completed', 'workflow': workflow, 'git': git_result}

    def _execute_non_code_task(self, task: dict[str, Any]) -> dict[str, Any]:
        before = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        workflow = self._run_workflow(self.repository_root, task)
        after = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if after != before:
            raise RuntimeError('non_code_task_modified_repository')
        self._audit(
            'autonomy_task_completed',
            {'task_id': task.get('id', ''), 'workflow': workflow},
        )
        return {'status': 'completed', 'workflow': workflow, 'git': {'status': 'not_required'}}

    def __call__(self, task: dict[str, Any]) -> dict[str, Any]:
        category = str(task.get('category', 'maintenance') or 'maintenance').lower()
        self._audit(
            'autonomy_task_started',
            {'task_id': task.get('id', ''), 'category': category},
        )
        if category in self.CODE_CATEGORIES:
            return self._execute_code_task(task)
        return self._execute_non_code_task(task)


__all__ = ['TrevorTaskExecutor']

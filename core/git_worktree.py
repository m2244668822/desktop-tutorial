from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable


class TrevorWorktreeManager:
    def __init__(self, repository_root: Path, data_root: Path) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.worktrees_root = Path(data_root).resolve() / 'worktrees'

    def _git(self, *arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ['git', *arguments],
            cwd=cwd or self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
        return normalized[:48] or 'task'

    def create(self, task_id: str, title: str) -> dict[str, str | Path]:
        branch = self._git('branch', '--show-current').stdout.strip()
        if branch != 'trevor/integration':
            raise RuntimeError('integration_branch_required')
        if self._git('status', '--porcelain').stdout.strip():
            raise RuntimeError('integration_worktree_dirty')

        safe_task_id = self._slug(task_id)
        task_branch = f'trevor/task/{safe_task_id}-{self._slug(title)}'
        worktree_path = self.worktrees_root / safe_task_id
        if worktree_path.exists():
            raise RuntimeError('task_worktree_exists')

        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        self._git(
            'worktree',
            'add',
            '-b',
            task_branch,
            str(worktree_path),
            'trevor/integration',
        )
        return {'branch': task_branch, 'path': worktree_path}

    def _integration_ready(self) -> None:
        branch = self._git('branch', '--show-current').stdout.strip()
        if branch != 'trevor/integration':
            raise RuntimeError('integration_branch_required')
        if self._git('status', '--porcelain').stdout.strip():
            raise RuntimeError('integration_worktree_dirty')

    def _validated_worktree(self, created: dict[str, Any]) -> tuple[str, Path]:
        branch = str(created.get('branch', '') or '').strip()
        path = Path(created.get('path', '')).resolve()
        if not branch.startswith('trevor/task/'):
            raise RuntimeError('invalid_task_branch')
        if not path.is_relative_to(self.worktrees_root):
            raise RuntimeError('invalid_task_worktree')
        actual_branch = self._git('branch', '--show-current', cwd=path).stdout.strip()
        if actual_branch != branch:
            raise RuntimeError('task_branch_mismatch')
        return branch, path

    def finalize(
        self,
        created: dict[str, Any],
        *,
        commit_message: str,
        validator: Callable[[Path], dict[str, Any] | bool],
    ) -> dict[str, Any]:
        branch, worktree_path = self._validated_worktree(created)
        self._git('diff', '--check', 'HEAD', cwd=worktree_path)
        validation = validator(worktree_path)
        valid = validation if isinstance(validation, bool) else bool(validation.get('ok'))
        if not valid:
            raise RuntimeError('validation_failed')

        status = self._git('status', '--porcelain', cwd=worktree_path).stdout.strip()
        if not status:
            self._git('worktree', 'remove', str(worktree_path))
            self._git('branch', '-D', branch)
            return {'status': 'no_changes', 'branch': branch}

        message = str(commit_message or '').strip()
        if not message:
            raise ValueError('commit_message_required')
        self._git('add', '--all', cwd=worktree_path)
        self._git('commit', '-m', message[:200], cwd=worktree_path)
        self._integration_ready()
        try:
            self._git('merge', '--no-ff', '--no-edit', branch)
        except subprocess.CalledProcessError as exc:
            subprocess.run(
                ['git', 'merge', '--abort'],
                cwd=self.repository_root,
                check=False,
                capture_output=True,
                text=True,
            )
            raise RuntimeError('integration_merge_failed') from exc
        commit = self._git('rev-parse', 'HEAD').stdout.strip()
        self._git('worktree', 'remove', str(worktree_path))
        self._git('branch', '-d', branch)
        return {'status': 'merged', 'branch': branch, 'commit': commit}

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from core.release_operations import record_operation


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class TrevorIntegrationPromoter:
    def __init__(
        self,
        repository_root: str | Path,
        data_root: str | Path,
        *,
        runner: CommandRunner = subprocess.run,
        validation_commands: Iterable[Sequence[str]] | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.data_root = Path(data_root).expanduser().resolve()
        self.runner = runner
        self.validation_commands = (
            tuple(tuple(command) for command in validation_commands)
            if validation_commands is not None
            else (
                (sys.executable, 'tools/scan_secrets.py'),
                (
                    sys.executable,
                    '-m',
                    'unittest',
                    'discover',
                    '-s',
                    'tests',
                    '-p',
                    'test_*.py',
                ),
            )
        )

    def _run(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return self.runner(
            [str(value) for value in command],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        )

    def _validate(self) -> list[dict[str, Any]]:
        self._run(('git', 'diff', '--check'))
        checks: list[dict[str, Any]] = []
        for command in self.validation_commands:
            process = self._run(command)
            checks.append(
                {
                    'command': [str(value) for value in command],
                    'returncode': int(process.returncode),
                }
            )
        return checks

    def promote(
        self,
        *,
        title: str = 'Trevor integration',
        body: str = 'Automated Trevor integration promotion guarded by required CI.',
    ) -> dict[str, Any]:
        branch = self._run(('git', 'branch', '--show-current')).stdout.strip()
        if branch != 'trevor/integration':
            raise RuntimeError('integration_branch_required')
        if self._run(('git', 'status', '--porcelain')).stdout.strip():
            raise RuntimeError('integration_worktree_dirty')

        checks = self._validate()
        self._run(('git', 'push', 'origin', 'trevor/integration'))
        listed = self._run(
            (
                'gh',
                'pr',
                'list',
                '--head',
                'trevor/integration',
                '--base',
                'main',
                '--state',
                'open',
                '--json',
                'number,url',
                '--limit',
                '1',
            )
        )
        try:
            pull_requests = json.loads(listed.stdout or '[]')
        except json.JSONDecodeError as exc:
            raise RuntimeError('pull_request_lookup_invalid') from exc

        created = not bool(pull_requests)
        if created:
            pull_request = self._run(
                (
                    'gh',
                    'pr',
                    'create',
                    '--head',
                    'trevor/integration',
                    '--base',
                    'main',
                    '--title',
                    str(title or 'Trevor integration')[:200],
                    '--body',
                    str(body or '')[:4000],
                )
            ).stdout.strip()
        else:
            first = pull_requests[0] if isinstance(pull_requests[0], dict) else {}
            pull_request = str(first.get('url', '') or '').strip()
        if not pull_request.startswith('https://github.com/'):
            raise RuntimeError('pull_request_url_invalid')

        self._run(('gh', 'pr', 'merge', pull_request, '--auto', '--merge'))
        record_operation(
            self.data_root,
            'git_merge',
            status='auto_merge_enabled',
            subject=pull_request,
            details={
                'head': 'trevor/integration',
                'base': 'main',
                'merge_method': 'merge',
                'required_ci': True,
                'created': created,
            },
        )
        return {
            'ok': True,
            'branch': branch,
            'pull_request': pull_request,
            'created': created,
            'auto_merge': True,
            'merge_method': 'merge',
            'checks': checks,
        }


__all__ = ['TrevorIntegrationPromoter']

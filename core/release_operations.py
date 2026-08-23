from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core.audit_chain import HashChainAuditLog


AUDITED_OPERATION_EVENTS = frozenset(
    {
        'git_merge',
        'model_switch',
        'permission_change',
        'deployment',
        'data_migration',
        'rollback',
    }
)


def record_operation(
    data_root: str | Path,
    event_type: str,
    *,
    status: str,
    subject: str = '',
    details: dict[str, Any] | None = None,
    actor: str = 'trevor',
) -> dict[str, Any]:
    event_name = str(event_type or '').strip().lower()
    if event_name not in AUDITED_OPERATION_EVENTS:
        raise ValueError('unsupported_operation_event')
    normalized_status = str(status or '').strip().lower()
    if not normalized_status:
        raise ValueError('operation_status_required')
    payload = {
        'status': normalized_status,
        'subject': str(subject or '').strip()[:240],
        'details': details or {},
    }
    return HashChainAuditLog(
        Path(data_root).expanduser().resolve() / 'audit' / 'events.jsonl'
    ).append(event_name, payload, actor=actor)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ['git', *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def revert_commit(
    repository: str | Path,
    commit: str,
    *,
    data_root: str | Path,
    reason: str,
    actor: str = 'trevor',
) -> dict[str, str]:
    root = Path(repository).expanduser().resolve()
    if not (root / '.git').exists():
        raise RuntimeError('git_repository_required')
    if _git(root, 'status', '--porcelain'):
        raise RuntimeError('rollback_requires_clean_worktree')
    branch = _git(root, 'branch', '--show-current')
    if branch not in {'main', 'trevor/integration'}:
        raise RuntimeError('rollback_branch_not_allowed')
    target = _git(root, 'rev-parse', '--verify', f'{str(commit).strip()}^{{commit}}')
    record_operation(
        data_root,
        'rollback',
        status='started',
        subject=target,
        details={'branch': branch, 'reason': reason},
        actor=actor,
    )
    try:
        _git(root, 'revert', '--no-edit', target)
    except subprocess.CalledProcessError as exc:
        subprocess.run(
            ['git', 'revert', '--abort'],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        record_operation(
            data_root,
            'rollback',
            status='failed',
            subject=target,
            details={'branch': branch, 'reason': reason, 'returncode': exc.returncode},
            actor=actor,
        )
        raise RuntimeError('git_revert_failed') from exc
    result_commit = _git(root, 'rev-parse', 'HEAD')
    record_operation(
        data_root,
        'rollback',
        status='completed',
        subject=target,
        details={
            'branch': branch,
            'reason': reason,
            'result_commit': result_commit,
        },
        actor=actor,
    )
    return {
        'status': 'completed',
        'branch': branch,
        'reverted_commit': target,
        'result_commit': result_commit,
    }


__all__ = ['AUDITED_OPERATION_EVENTS', 'record_operation', 'revert_commit']

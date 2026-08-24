from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def build_runtime_capability_manifest(
    workspace: str | Path,
    *,
    memory_ready: bool,
    provider_status: Mapping[str, Any] | None = None,
    autonomy_status: Mapping[str, Any] | None = None,
    control_plane_status: Mapping[str, Any] | None = None,
    web_search_ready: bool = False,
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    provider_payload = _mapping(provider_status)
    autonomy_payload = _mapping(autonomy_status)
    control_payload = _mapping(control_plane_status)
    skill_names = sorted(
        {
            path.parent.name
            for base in (root / 'skills', root / '.gemini' / 'skills')
            if base.is_dir()
            for path in base.glob('*/SKILL.md')
        }
    )
    enabled_providers = sorted(
        {
            str(item.get('provider', '') or '').strip().lower()
            for item in provider_payload.get('providers', [])
            if isinstance(item, Mapping)
            and bool(item.get('enabled'))
            and str(item.get('provider', '') or '').strip()
        }
    )
    workspace_readable = bool(root.is_dir() and os.access(root, os.R_OK))
    workspace_writable = bool(root.is_dir() and os.access(root, os.W_OK))
    autonomy_ready = str(
        autonomy_payload.get('daemon_status', autonomy_payload.get('status', '')) or ''
    ).strip().lower() == 'running' or bool(autonomy_payload.get('ready'))
    control_plane_ready = bool(
        control_payload.get('ok')
        and control_payload.get('task_forwarding_configured', True)
    )

    return {
        'schema_version': 1,
        'identity': {'agent': 'trevor', 'role': '崔佛'},
        'authority': {
            'controller': 'nvidia',
            'external_candidates': 'read_only',
        },
        'capabilities': {
            'skill_packages': {
                'ready': bool(skill_names),
                'count': len(skill_names),
                'names': skill_names,
                'installation': 'controlled_workflow',
                'managed_install_ready': bool(control_plane_ready and workspace_writable),
            },
            'workspace_files': {
                'ready': workspace_readable,
                'write_ready': workspace_writable,
                'scope': 'workspace_controlled',
            },
            'external_apis': {
                'ready': bool(enabled_providers),
                'providers': enabled_providers,
                'scope': 'registered_providers_only',
            },
            'persistent_memory': {
                'ready': bool(memory_ready),
                'write_authority': 'nvidia_control_core',
            },
            'autonomous_tasks': {
                'ready': autonomy_ready,
                'max_concurrent': 1,
            },
            'control_plane': {
                'ready': control_plane_ready,
                'scope': 'approved_execution_and_workflows',
            },
            'git': {
                'ready': (root / '.git').exists(),
                'scope': 'protected_workflow',
            },
            'realtime_web_search': {
                'ready': bool(web_search_ready),
                'scope': 'registered_adapter_only',
            },
        },
        'boundaries': {
            'provider_candidate_calls_execute_tools': False,
            'candidate_seat_limit_is_trevor_limit': False,
            'unverified_capability_claims_allowed': False,
        },
    }


def is_runtime_capability_query(message: str) -> bool:
    text = str(message or '').strip().lower()
    if not text:
        return False
    install_commands = (
        '直接幫我安裝',
        '幫我安裝',
        '請安裝',
        '開始安裝',
        '執行安裝',
        'install this skill',
        'install the skill',
    )
    if any(marker in text for marker in install_commands):
        return False
    query_markers = (
        '有哪些能力',
        '能力清單',
        '能力狀態',
        '缺失能力',
        '技能安裝',
        '外掛式技能',
        '模型內建',
        '能不能存取',
        '是否能存取',
        '檔案系統存取',
        '外部 api',
        '長期記憶',
        '即時聯網',
        '聯網搜尋',
        'what can you do',
        'capability status',
    )
    return any(marker in text for marker in query_markers)


def render_runtime_capability_reply(manifest: Mapping[str, Any]) -> str:
    payload = _mapping(manifest)
    capabilities = _mapping(payload.get('capabilities'))
    skills = _mapping(capabilities.get('skill_packages'))
    workspace = _mapping(capabilities.get('workspace_files'))
    external_apis = _mapping(capabilities.get('external_apis'))
    memory = _mapping(capabilities.get('persistent_memory'))
    autonomy = _mapping(capabilities.get('autonomous_tasks'))
    control_plane = _mapping(capabilities.get('control_plane'))
    web_search = _mapping(capabilities.get('realtime_web_search'))
    provider_names = ', '.join(external_apis.get('providers', [])) or '無已啟用供應商'

    lines = [
        '【崔佛】能力更正：先前把「外部候選模型的唯讀限制」誤當成崔佛整體限制。',
        (
            f"- 本機技能包：{int(skills.get('count', 0) or 0)} 個已發現；"
            '可由 NVIDIA 控制核心透過受控工作流新增或更新，不是全部能力都只靠模型內建。'
        ),
        (
            '- 工作區檔案：可用（受控讀寫）。'
            if workspace.get('ready')
            else '- 工作區檔案：目前不可用。'
        ),
        (
            f'- 外部 API：可用（{provider_names}）。'
            if external_apis.get('ready')
            else '- 外部 API：目前沒有已啟用供應商。'
        ),
        (
            '- 持久記憶：可用，由控制核心統一讀寫。'
            if memory.get('ready')
            else '- 持久記憶：目前未就緒。'
        ),
        (
            '- 自主任務：運行中，單次最多一項任務。'
            if autonomy.get('ready')
            else '- 自主任務：目前未運行。'
        ),
        (
            '- 控制平面：可用，可承接核准後的工具與工作流任務。'
            if control_plane.get('ready')
            else '- 控制平面：目前降級，改走本機回退流程。'
        ),
        (
            '- 專用即時網頁搜尋：可用（僅透過已登記適配器）。'
            if web_search.get('ready')
            else '- 專用即時網頁搜尋：尚未登記為可用工具；不會假裝已完成即時搜尋。'
        ),
        '外部 Gemini、Groq 等候選席位仍然沒有工具或記憶寫入權，但這不代表崔佛沒有這些能力。',
    ]
    return '\n'.join(lines)


__all__ = [
    'build_runtime_capability_manifest',
    'is_runtime_capability_query',
    'render_runtime_capability_reply',
]

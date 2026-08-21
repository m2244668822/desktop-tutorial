from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


TREVOR_AGENT_ID = 'trevor'
TREVOR_DISPLAY_NAME = '崔佛'
TREVOR_SCHEMA_VERSION = 2
CAPABILITY_MODES = (
    'general',
    'coding',
    'research',
    'security',
    'content',
    'learning',
)

CAPABILITY_LABELS = {
    'general': '一般',
    'coding': '程式',
    'research': '研究',
    'security': '安全',
    'content': '內容',
    'learning': '學習',
}

LEGACY_ALIAS_MODES = {
    'dispatcher': 'general',
    'manager': 'general',
    'orchestrator': 'general',
    'proclaimer': 'general',
    'prophet': 'general',
    'general': 'general',
    '總管': 'general',
    '總管中樞': 'general',
    '申言者': 'general',
    '通用': 'general',
    'engineer': 'coding',
    '工程師': 'coding',
    'researcher': 'research',
    '研究員': 'research',
    '研究學習中樞': 'research',
    'whitehat': 'security',
    'hat': 'security',
    '帽子': 'security',
    '白帽駭客': 'security',
    'xiaobian': 'content',
    'editor': 'content',
    '小編': 'content',
    '小編設計師': 'content',
    'learner': 'learning',
    '學習器': 'learning',
    'relay': 'general',
    '中繼器': 'general',
}


@dataclass(frozen=True)
class TrevorIdentity:
    agent: str = TREVOR_AGENT_ID
    role: str = TREVOR_DISPLAY_NAME
    capability_mode: str = 'general'
    schema_version: int = TREVOR_SCHEMA_VERSION
    deprecated_alias: bool = False
    source_alias: str = ''

    def public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['id'] = payload.pop('agent')
        payload['display_name'] = payload.pop('role')
        payload.pop('deprecated_alias', None)
        payload.pop('source_alias', None)
        return payload


def _clean_alias(value: str | None) -> str:
    return str(value or '').strip()


def capability_mode_for_alias(value: str | None) -> str:
    alias = _clean_alias(value)
    if alias in CAPABILITY_MODES:
        return alias
    return LEGACY_ALIAS_MODES.get(alias, LEGACY_ALIAS_MODES.get(alias.lower(), 'general'))


def normalize_trevor_identity(
    *,
    agent: str | None = None,
    role: str | None = None,
    capability_mode: str | None = None,
) -> TrevorIdentity:
    requested_mode = _clean_alias(capability_mode).lower()
    source_alias = _clean_alias(agent) or _clean_alias(role)
    if requested_mode in CAPABILITY_MODES:
        mode = requested_mode
    else:
        mode = capability_mode_for_alias(agent or role)
    canonical_aliases = {'', TREVOR_AGENT_ID, TREVOR_DISPLAY_NAME}
    return TrevorIdentity(
        capability_mode=mode,
        deprecated_alias=source_alias not in canonical_aliases,
        source_alias=source_alias,
    )


def decorate_trevor_response(
    payload: dict[str, Any] | None,
    *,
    requested_agent: str | None = None,
    requested_role: str | None = None,
    capability_mode: str | None = None,
) -> dict[str, Any]:
    result = dict(payload or {})
    normalized = normalize_trevor_identity(
        agent=requested_agent,
        role=requested_role,
        capability_mode=capability_mode,
    )
    result['agent'] = normalized.agent
    result['role'] = normalized.role
    result['identity'] = normalized.public_dict()
    deprecations = list(result.get('deprecations') or [])
    if normalized.deprecated_alias:
        deprecations.append(
            {
                'code': 'legacy_agent_alias',
                'value': normalized.source_alias,
                'replacement': TREVOR_AGENT_ID,
                'remove_after_schema_version': TREVOR_SCHEMA_VERSION,
            }
        )
    if deprecations:
        result['deprecations'] = deprecations
    return result


def canonicalize_trevor_reply(value: str | None, capability_mode: str = 'general') -> str:
    result = str(value or '')
    label = CAPABILITY_LABELS.get(capability_mode, CAPABILITY_LABELS['general'])
    replacement = f'【{TREVOR_DISPLAY_NAME}｜{label}】'
    for alias in LEGACY_ALIAS_MODES:
        result = result.replace(f'【{alias}】', replacement)
    return result


__all__ = [
    'CAPABILITY_MODES',
    'CAPABILITY_LABELS',
    'LEGACY_ALIAS_MODES',
    'TREVOR_AGENT_ID',
    'TREVOR_DISPLAY_NAME',
    'TREVOR_SCHEMA_VERSION',
    'TrevorIdentity',
    'capability_mode_for_alias',
    'canonicalize_trevor_reply',
    'decorate_trevor_response',
    'normalize_trevor_identity',
]

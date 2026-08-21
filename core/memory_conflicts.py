from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SOURCE_PRECEDENCE = {
    'user_explicit': 100,
    'system_policy': 90,
    'verified_observation': 70,
    'provider_verified': 60,
    'model_inferred': 40,
    'legacy': 20,
    'unknown': 0,
}

RESTRICTIVE_VALUES = {'deny', 'denied', 'forbid', 'forbidden', 'blocked', 'false', 'off', '0'}


def _timestamp(value: Any) -> float:
    raw = str(value or '').strip()
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return 0.0


def _normalized(record: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(record)
    result['key'] = str(result.get('key', '') or '').strip()
    result['source'] = str(result.get('source', 'unknown') or 'unknown').strip().lower()
    result['priority'] = int(result.get('priority', 0) or 0)
    result['confidence'] = max(0.0, min(1.0, float(result.get('confidence', 0.5) or 0.5)))
    result['updated_at'] = str(result.get('updated_at', '') or '')
    return result


@dataclass(frozen=True)
class ConflictDecision:
    winner: dict[str, Any]
    loser: dict[str, Any] | None
    conflict: bool
    reason: str


class MemoryConflictResolver:
    def resolve(
        self,
        existing: Mapping[str, Any] | None,
        incoming: Mapping[str, Any],
    ) -> ConflictDecision:
        candidate = _normalized(incoming)
        if not existing:
            return ConflictDecision(candidate, None, False, 'new_value')
        current = _normalized(existing)
        if current.get('value') == candidate.get('value'):
            merged = dict(current)
            merged['confidence'] = max(current['confidence'], candidate['confidence'])
            if _timestamp(candidate['updated_at']) > _timestamp(current['updated_at']):
                merged['updated_at'] = candidate['updated_at']
            return ConflictDecision(merged, None, False, 'same_value')

        key = candidate.get('key') or current.get('key') or ''
        if key.startswith(('permission.', 'safety.', 'privacy.')):
            current_restrictive = str(current.get('value', '')).strip().lower() in RESTRICTIVE_VALUES
            candidate_restrictive = str(candidate.get('value', '')).strip().lower() in RESTRICTIVE_VALUES
            if current_restrictive != candidate_restrictive:
                winner, loser = (current, candidate) if current_restrictive else (candidate, current)
                return ConflictDecision(winner, loser, True, 'safety_deny_wins')

        current_source = SOURCE_PRECEDENCE.get(current['source'], 0)
        candidate_source = SOURCE_PRECEDENCE.get(candidate['source'], 0)
        if current_source != candidate_source:
            winner, loser = (
                (current, candidate) if current_source > candidate_source else (candidate, current)
            )
            return ConflictDecision(winner, loser, True, 'source_precedence')
        if current['priority'] != candidate['priority']:
            winner, loser = (
                (current, candidate)
                if current['priority'] > candidate['priority']
                else (candidate, current)
            )
            return ConflictDecision(winner, loser, True, 'priority')
        winner, loser = (
            (candidate, current)
            if _timestamp(candidate['updated_at']) >= _timestamp(current['updated_at'])
            else (current, candidate)
        )
        return ConflictDecision(winner, loser, True, 'newer_value')

    def resolve_many(self, records: Iterable[Mapping[str, Any]]) -> dict[str, ConflictDecision]:
        decisions: dict[str, ConflictDecision] = {}
        winners: dict[str, dict[str, Any]] = {}
        for record in records:
            key = str(record.get('key', '') or '').strip()
            if not key:
                continue
            decision = self.resolve(winners.get(key), record)
            winners[key] = decision.winner
            decisions[key] = decision
        return decisions


__all__ = ['ConflictDecision', 'MemoryConflictResolver', 'SOURCE_PRECEDENCE']

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from core.content_sanitizer import ExternalContentSanitizer
from core.provider_registry import ProviderCallError, ProviderRegistry, ProviderSpec


BASE_PROVIDERS = ('nvidia', 'gemini', 'groq', 'cerebras')
ARBITER_PROVIDERS = ('openrouter', 'cloudflare')
HARD_GATES = ('safe', 'privacy_ok', 'format_ok', 'tests_ok')


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _claim_signature(claim: Any) -> tuple[str, str]:
    if isinstance(claim, Mapping):
        return (
            str(claim.get('key', claim.get('subject', ''))).strip().lower(),
            str(claim.get('value', claim.get('object', ''))).strip().lower(),
        )
    return ('claim', str(claim or '').strip().lower())


@dataclass
class Candidate:
    provider: str
    answer: str
    claims: list[Any]
    evidence: list[Any]
    assumptions: list[Any]
    confidence: float
    quality: dict[str, Any]
    model: str = ''
    used_model_fallback: bool = False
    score: float = 0.0
    consistency: float = 0.0

    @property
    def passes_gates(self) -> bool:
        return all(bool(self.quality.get(gate, False)) for gate in HARD_GATES)


@dataclass
class CouncilResult:
    answer: str
    metadata: dict[str, Any]
    evidence_summary: list[Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            'answer': self.answer,
            'deliberation': {
                **self.metadata,
                'evidence_summary': self.evidence_summary,
            },
        }


class DeliberationCouncil:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        runner: Callable[[ProviderSpec, dict[str, Any]], Any],
        sanitizer: ExternalContentSanitizer | None = None,
        polisher: Callable[[ProviderSpec, dict[str, Any]], Any] | None = None,
        audit_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ):
        self.registry = registry
        self.runner = runner
        self.sanitizer = sanitizer or ExternalContentSanitizer()
        self.polisher = polisher
        self.audit_callback = audit_callback
        self._rotation_index = 0
        self._last_selected_provider = ''

    def _providers_for_mode(self, mode: str) -> tuple[list[str], list[str]]:
        requested = str(mode or 'auto').strip().lower()
        if requested == 'auto':
            requested = 'cross_check'
        if requested == 'fast':
            desired = ['nvidia']
        elif requested == 'cross_check':
            externals = self.registry.available(BASE_PROVIDERS[1:])
            external = []
            if externals:
                external = [externals[self._rotation_index % len(externals)]]
                self._rotation_index += 1
            desired = ['nvidia', *external]
        else:
            requested = 'rigorous'
            desired = list(BASE_PROVIDERS)
        return self.registry.available(desired), desired

    @staticmethod
    def _parse_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, Mapping):
            return dict(payload)
        text = str(payload or '').strip()
        if text.startswith('```'):
            text = text.strip('`').removeprefix('json').strip()
        parsed = json.loads(text)
        return dict(parsed) if isinstance(parsed, Mapping) else {}

    def _build_candidate(
        self,
        provider: str,
        payload: Any,
        *,
        model: str = '',
        used_model_fallback: bool = False,
    ) -> Candidate:
        parsed = self._parse_payload(payload)
        quality_payload = parsed.get('quality')
        if not isinstance(quality_payload, Mapping):
            raise ValueError('candidate_quality_object_required')
        quality = dict(quality_payload)
        return Candidate(
            provider=provider,
            answer=str(parsed.get('answer', '') or '').strip(),
            claims=list(parsed.get('claims') or []),
            evidence=list(parsed.get('evidence') or []),
            assumptions=list(parsed.get('assumptions') or []),
            confidence=_clamp(parsed.get('confidence'), 0.0),
            quality=quality,
            model=str(model or ''),
            used_model_fallback=bool(used_model_fallback),
        )

    @staticmethod
    def _consistency_scores(candidates: Iterable[Candidate]) -> dict[str, float]:
        items = list(candidates)
        if len(items) <= 1:
            return {item.provider: 1.0 for item in items}
        signatures = {
            item.provider: set(_claim_signature(claim) for claim in item.claims)
            for item in items
        }
        scores: dict[str, float] = {}
        for item in items:
            similarities = []
            own = signatures[item.provider]
            for other in items:
                if other.provider == item.provider:
                    continue
                theirs = signatures[other.provider]
                union = own | theirs
                similarities.append(len(own & theirs) / len(union) if union else 1.0)
            scores[item.provider] = sum(similarities) / len(similarities)
        return scores

    @staticmethod
    def _contradictions(candidates: Iterable[Candidate]) -> list[dict[str, Any]]:
        values_by_key: dict[str, dict[str, list[str]]] = {}
        for item in candidates:
            for claim in item.claims:
                key, value = _claim_signature(claim)
                if not key or not value:
                    continue
                values_by_key.setdefault(key, {}).setdefault(value, []).append(item.provider)
        contradictions = []
        for key, values in values_by_key.items():
            if len(values) > 1:
                contradictions.append({'claim': key, 'values': sorted(values)})
        return contradictions

    def _score(self, candidate: Candidate) -> float:
        evidence = _clamp(candidate.quality.get('evidence_verification'), 0.0)
        requirement = _clamp(candidate.quality.get('requirement_fit'), 0.0)
        reliability = self.registry.state(candidate.provider).recent_reliability
        return (
            evidence * 0.45
            + requirement * 0.25
            + candidate.consistency * 0.20
            + reliability * 0.10
        )

    def _run_arbiter(
        self,
        candidates: list[Candidate],
        contradictions: list[dict[str, Any]],
    ) -> tuple[str, str]:
        available = self.registry.available(ARBITER_PROVIDERS)
        if not available:
            return '', ''
        arbiter = available[0]
        request = self.registry.build_dialogue_request(
            arbiter,
            {
                'candidates': [
                    {
                        'provider': item.provider,
                        'claims': item.claims,
                        'evidence': item.evidence,
                        'confidence': item.confidence,
                        'score': round(item.score, 4),
                    }
                    for item in candidates
                ],
                'contradictions': contradictions,
            },
        )
        request['request_type'] = 'arbitration'
        try:
            parsed = self._parse_payload(self.runner(self.registry.get(arbiter), request))
            selected = str(parsed.get('selected_provider', '') or '').strip().lower()
            if selected in {item.provider for item in candidates}:
                self.registry.record_success(arbiter)
                return selected, arbiter
        except ProviderCallError as exc:
            self.registry.record_failure(arbiter, exc.status_code)
        except Exception:
            self.registry.record_failure(arbiter)
        return '', arbiter

    def _polish(self, winner: Candidate, candidates: list[Candidate]) -> str:
        if self.polisher is None:
            return winner.answer
        winner_family = self.registry.model_family_for(winner.provider)
        choices = [
            item.provider
            for item in candidates
            if item.provider != winner.provider
            and self.registry.model_family_for(item.provider) != winner_family
        ]
        if not choices:
            return winner.answer
        provider = choices[0]
        request = self.registry.build_dialogue_request(
            provider,
            {
                'answer': winner.answer,
                'verified_claims': winner.claims,
                'instruction': 'Improve clarity only. Do not add claims.',
            },
        )
        request['request_type'] = 'polish'
        try:
            parsed = self._parse_payload(self.polisher(self.registry.get(provider), request))
        except Exception:
            return winner.answer
        polished_claims = {_claim_signature(claim) for claim in parsed.get('claims', [])}
        verified_claims = {_claim_signature(claim) for claim in winner.claims}
        if not polished_claims.issubset(verified_claims):
            return winner.answer
        return str(parsed.get('answer', '') or '').strip() or winner.answer

    def deliberate(
        self,
        message: str,
        *,
        mode: str = 'auto',
        capability_mode: str = 'general',
        shadow: bool = False,
        conversation: Iterable[Mapping[str, Any]] = (),
        memory_context: str = '',
        attachments: Iterable[Mapping[str, Any]] = (),
    ) -> CouncilResult:
        selected, desired = self._providers_for_mode(mode)
        sanitized = self.sanitizer.sanitize(
            message=message,
            conversation=conversation,
            memory_context=memory_context,
            attachments=attachments,
        )
        sanitized.payload['capability_mode'] = str(capability_mode or 'general')
        candidates: list[Candidate] = []
        unavailable = [name for name in desired if name not in selected]
        rejected: list[str] = []
        attempted: list[str] = []

        for provider in selected:
            attempted.append(provider)
            purpose = (
                'coding'
                if provider == 'nvidia' and capability_mode == 'coding'
                else 'dialogue'
            )
            request = self.registry.build_dialogue_request(
                provider,
                sanitized.payload,
                purpose=purpose,
            )
            started = time.perf_counter()
            try:
                requests = [request]
                for fallback_model in self.registry.fallback_models_for(provider, purpose):
                    fallback_request = dict(request)
                    fallback_request['model'] = fallback_model
                    requests.append(fallback_request)
                candidate = None
                format_rejected = False
                for request_index, provider_request in enumerate(requests):
                    try:
                        payload = self.runner(
                            self.registry.get(provider), provider_request
                        )
                    except ProviderCallError as exc:
                        retryable = bool(
                            exc.status_code == 408
                            or (exc.status_code is not None and exc.status_code >= 500)
                        )
                        if retryable and request_index + 1 < len(requests):
                            continue
                        raise
                    try:
                        candidate = self._build_candidate(
                            provider,
                            payload,
                            model=str(provider_request.get('model', '') or ''),
                            used_model_fallback=provider_request is not request,
                        )
                    except (TypeError, ValueError, json.JSONDecodeError):
                        format_rejected = True
                        if request_index + 1 < len(requests):
                            continue
                        break
                    break
                if candidate is None and format_rejected:
                    self.registry.record_failure(provider)
                    rejected.append(provider)
                    continue
                if candidate is None:
                    raise RuntimeError('candidate_missing')
                latency_ms = (time.perf_counter() - started) * 1000
                self.registry.record_success(provider, latency_ms)
                if not candidate.answer or not candidate.passes_gates:
                    rejected.append(provider)
                    continue
                candidates.append(candidate)
            except ProviderCallError as exc:
                unavailable.append(provider)
                self.registry.record_failure(provider, exc.status_code)
            except Exception:
                unavailable.append(provider)
                self.registry.record_failure(provider)

        consistency = self._consistency_scores(candidates)
        for item in candidates:
            item.consistency = consistency.get(item.provider, 0.0)
            item.score = self._score(item)
        candidates.sort(key=lambda item: (item.score, item.confidence), reverse=True)

        if not candidates:
            return CouncilResult(
                answer='',
                metadata={
                    'mode': str(mode or 'auto'),
                    'status': 'unavailable',
                    'providers': attempted,
                    'unavailable_providers': sorted(set(unavailable)),
                    'rejected_providers': sorted(set(rejected)),
                    'agreement_score': 0.0,
                    'confidence': 0.0,
                    'arbitrated': False,
                    'arbiter': '',
                    'major_disagreement': ['no_eligible_candidate'],
                },
                evidence_summary=[],
            )

        contradictions = self._contradictions(candidates)
        top = candidates[0]
        recommendation = top.provider
        margin = top.score - candidates[1].score if len(candidates) > 1 else 1.0
        disagreement = []
        if top.score < 0.70:
            disagreement.append('low_score')
        if len(candidates) > 1 and margin < 0.05:
            disagreement.append('top_score_margin')
        if contradictions:
            disagreement.append('contradictory_claims')

        arbitrated = False
        arbiter = ''
        if disagreement and not shadow:
            selected_provider, arbiter = self._run_arbiter(candidates, contradictions)
            if selected_provider:
                top = next(item for item in candidates if item.provider == selected_provider)
                arbitrated = True

        if shadow:
            nvidia_candidate = next(
                (item for item in candidates if item.provider == 'nvidia'),
                None,
            )
            if nvidia_candidate is not None:
                top = nvidia_candidate
        answer = top.answer if shadow else self._polish(top, candidates)
        if shadow:
            status = 'shadow_degraded' if unavailable or len(attempted) < len(desired) else 'shadow'
        else:
            status = (
                'degraded'
                if unavailable or len(attempted) < len(desired) or top.used_model_fallback
                else 'complete'
            )
        agreement_score = sum(item.consistency for item in candidates) / len(candidates)
        evidence_summary = [
            evidence.get('summary', '') if isinstance(evidence, Mapping) else str(evidence)
            for evidence in top.evidence
            if (evidence.get('verified', False) if isinstance(evidence, Mapping) else True)
        ]
        if self.audit_callback is not None and top.provider != self._last_selected_provider:
            self.audit_callback(
                'model_switch',
                {
                    'from_provider': self._last_selected_provider,
                    'to_provider': top.provider,
                    'model': top.model or self.registry.model_for(top.provider),
                    'mode': str(mode or 'auto'),
                    'shadow': bool(shadow),
                },
            )
            self._last_selected_provider = top.provider
        return CouncilResult(
            answer=answer,
            metadata={
                'mode': str(mode or 'auto'),
                'status': status,
                'providers': attempted,
                'unavailable_providers': sorted(set(unavailable)),
                'rejected_providers': sorted(set(rejected)),
                'agreement_score': round(agreement_score, 4),
                'confidence': round(top.confidence, 4),
                'selected_provider': top.provider,
                'selected_model': top.model or self.registry.model_for(top.provider),
                'provider_model_fallback': top.used_model_fallback,
                'shadow_recommendation': recommendation if shadow else '',
                'score': round(top.score, 4),
                'arbitrated': arbitrated,
                'arbiter': arbiter,
                'major_disagreement': disagreement,
                'contradictions': contradictions,
                'redaction_count': sanitized.redaction_count,
                'degraded_paid_fallback': False,
            },
            evidence_summary=evidence_summary,
        )


__all__ = ['CouncilResult', 'DeliberationCouncil']

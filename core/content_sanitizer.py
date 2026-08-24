from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        'secret_assignment',
        re.compile(
            r'(?i)\b(?:[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD))\s*[:=]\s*[^\s,，;；]+',
        ),
        '[REDACTED_SECRET]',
    ),
    (
        'bearer_token',
        re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}'),
        'Bearer [REDACTED_TOKEN]',
    ),
    (
        'known_key',
        re.compile(
            r'\b(?:'
            r'(?:nvapi-|gsk_|sk-|AIza)[A-Za-z0-9._-]{8,}'
            r'|gh[pousr]_[A-Za-z0-9]{20,}'
            r'|AKIA[0-9A-Z]{16}'
            r'|xox[baprs]-[A-Za-z0-9-]{20,}'
            r')\b'
        ),
        '[REDACTED_SECRET]',
    ),
    (
        'private_key',
        re.compile(
            r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?'
            r'-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
            re.DOTALL,
        ),
        '[REDACTED_PRIVATE_KEY]',
    ),
    (
        'email',
        re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.IGNORECASE),
        '[REDACTED_EMAIL]',
    ),
    (
        'private_path',
        re.compile(
            r'(?:(?:file://)?/(?:Users|Volumes|home)/[^\s,，;；]+|[A-Za-z]:\\[^\s,，;；]+)',
            re.IGNORECASE,
        ),
        '[REDACTED_PATH]',
    ),
    (
        'phone',
        re.compile(r'(?<!\w)(?:\+?886[\s-]?)?0?9\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\w)'),
        '[REDACTED_PHONE]',
    ),
    (
        'ipv4',
        re.compile(r'(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)'),
        '[REDACTED_IP]',
    ),
)


@dataclass(frozen=True)
class SanitizationResult:
    payload: dict[str, Any]
    redactions: dict[str, int]

    @property
    def redaction_count(self) -> int:
        return sum(self.redactions.values())


class ExternalContentSanitizer:
    def _sanitize_text(self, value: Any, counts: dict[str, int]) -> str:
        result = str(value or '')
        for name, pattern, replacement in _REDACTION_PATTERNS:
            result, count = pattern.subn(replacement, result)
            if count:
                counts[name] = counts.get(name, 0) + count
        return result

    def _sanitize_messages(
        self,
        conversation: Iterable[Mapping[str, Any]],
        counts: dict[str, int],
    ) -> list[dict[str, str]]:
        messages = []
        for item in conversation:
            if not isinstance(item, Mapping):
                continue
            role = str(item.get('role', 'user')).strip().lower()
            if role not in {'user', 'assistant'}:
                role = 'user'
            content = self._sanitize_text(item.get('content', ''), counts).strip()
            if content:
                messages.append({'role': role, 'content': content})
        return messages

    def _sanitize_attachments(
        self,
        attachments: Iterable[Mapping[str, Any]],
        counts: dict[str, int],
    ) -> list[dict[str, Any]]:
        safe_attachments = []
        for item in attachments:
            if not isinstance(item, Mapping):
                continue
            safe_item: dict[str, Any] = {
                'name': self._sanitize_text(item.get('name', 'attachment'), counts),
            }
            mime_type = str(item.get('mime_type', item.get('type', '')) or '').strip()
            if mime_type:
                safe_item['mime_type'] = mime_type[:120]
            size = item.get('size')
            if isinstance(size, int) and size >= 0:
                safe_item['size'] = size
            if any(item.get(key) for key in ('url', 'path', 'data', 'content')):
                counts['attachment_payload'] = counts.get('attachment_payload', 0) + 1
            safe_attachments.append(safe_item)
        return safe_attachments

    def sanitize(
        self,
        *,
        message: str,
        conversation: Iterable[Mapping[str, Any]] = (),
        memory_context: str = '',
        attachments: Iterable[Mapping[str, Any]] = (),
        **_discarded_mutating_interfaces: Any,
    ) -> SanitizationResult:
        counts: dict[str, int] = {}
        payload = {
            'message': self._sanitize_text(message, counts),
            'conversation': self._sanitize_messages(conversation, counts),
            'memory_context': self._sanitize_text(memory_context, counts),
            'attachments': self._sanitize_attachments(attachments, counts),
        }
        return SanitizationResult(payload=payload, redactions=counts)


__all__ = ['ExternalContentSanitizer', 'SanitizationResult']

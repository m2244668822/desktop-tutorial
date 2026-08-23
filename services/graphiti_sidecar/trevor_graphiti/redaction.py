from __future__ import annotations

import re


PATTERNS = (
    (
        re.compile(
            r'(?i)\b(?:[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD))\s*[:=]\s*[^\s,，;；]+'
        ),
        '[REDACTED_SECRET]',
    ),
    (re.compile(r'\b(?:nvapi-|gsk_|sk-|AIza)[A-Za-z0-9._-]{8,}\b'), '[REDACTED_SECRET]'),
    (
        re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.IGNORECASE),
        '[REDACTED_EMAIL]',
    ),
    (
        re.compile(r'(?:(?:file://)?/(?:Users|Volumes|home)/[^\s,，;；]+|[A-Za-z]:\\[^\s,，;；]+)'),
        '[REDACTED_PATH]',
    ),
    (re.compile(r'(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)'), '[REDACTED_IP]'),
)


def redact_text(value: str) -> tuple[str, int]:
    result = str(value or '')
    count = 0
    for pattern, replacement in PATTERNS:
        result, matches = pattern.subn(replacement, result)
        count += matches
    return result, count


__all__ = ['redact_text']

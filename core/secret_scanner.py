from __future__ import annotations

import hashlib
import math
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Iterable


SECRET_PATTERNS = (
    ('private_key', re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----')),
    ('nvidia_api_key', re.compile(r'\bnvapi-[A-Za-z0-9_-]{20,}\b')),
    ('google_api_key', re.compile(r'\bAIza[A-Za-z0-9_-]{30,}\b')),
    ('groq_api_key', re.compile(r'\bgsk_[A-Za-z0-9_-]{20,}\b')),
    ('openai_api_key', re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b')),
    ('github_token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b')),
    ('aws_access_key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('slack_token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b')),
)

SECRET_NAME = r'[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|CLIENT_SECRET|PASSWORD)'
QUOTED_ASSIGNMENT_PATTERN = re.compile(
    rf'(?i)[\'\"]?{SECRET_NAME}[\'\"]?\s*[:=]\s*(?P<quote>[\'\"])'
    rf'(?P<value>[^\'\"\r\n]{{8,}})(?P=quote)'
)
ENV_ASSIGNMENT_PATTERN = re.compile(
    rf'(?i)^\s*(?:export\s+)?{SECRET_NAME}\s*=\s*([^\s#]+)\s*$'
)

EXCLUDED_PARTS = frozenset(
    {
        '.git',
        '.venv',
        'node_modules',
        'vendor',
        '__pycache__',
        'data',
        'data_hdd_storage',
        'logs',
        'tmp',
        'archive',
    }
)


class SecretScanner:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    @staticmethod
    def _placeholder(value: str) -> bool:
        normalized = value.strip().strip('\'\"').lower()
        return (
            not normalized
            or normalized.startswith(('$', '${'))
            or any(marker in normalized for marker in ('{', '}', 'os.getenv', 'environ', 'getenv('))
            or any(
                marker in normalized
                for marker in ('your_', '_here', 'example', 'placeholder', 'changeme', 'redacted', 'fake', 'dummy')
            )
        )

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            return str(path.resolve())

    def _scan_parts(self, path: Path) -> tuple[str, ...]:
        try:
            return path.resolve().relative_to(self.root).parts
        except ValueError:
            return (path.name,)

    @staticmethod
    def _looks_sensitive_literal(value: str) -> bool:
        candidate = value.strip().strip('\'\"')
        if len(candidate) < 24 or any(token in candidate for token in ('(', ')', '{', '}', '$', '://')):
            return False
        character_classes = sum(
            (
                any(character.islower() for character in candidate),
                any(character.isupper() for character in candidate),
                any(character.isdigit() for character in candidate),
                any(not character.isalnum() for character in candidate),
            )
        )
        if character_classes < 3:
            return False
        counts = Counter(candidate)
        entropy = -sum(
            (count / len(candidate)) * math.log2(count / len(candidate))
            for count in counts.values()
        )
        return entropy >= 3.5

    def _finding(self, path: Path, line: int, rule: str, value: str) -> dict[str, object]:
        return {
            'path': self._display_path(path),
            'line': line,
            'rule': rule,
            'fingerprint': hashlib.sha256(value.encode('utf-8')).hexdigest()[:12],
        }

    def scan_paths(self, paths: Iterable[str | Path]) -> dict[str, object]:
        findings: list[dict[str, object]] = []
        scanned = 0
        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            if any(part in EXCLUDED_PARTS for part in self._scan_parts(path)):
                continue
            try:
                content = path.read_bytes()
            except OSError:
                continue
            if b'\x00' in content:
                continue
            text = content.decode('utf-8', errors='replace')
            scanned += 1
            for line_number, line in enumerate(text.splitlines(), start=1):
                known_secret_found = False
                for rule, pattern in SECRET_PATTERNS:
                    match = pattern.search(line)
                    if match and not self._placeholder(match.group(0)):
                        findings.append(
                            self._finding(path, line_number, rule, match.group(0))
                        )
                        known_secret_found = True
                if not known_secret_found:
                    assignments = []
                    quoted = QUOTED_ASSIGNMENT_PATTERN.search(line)
                    if quoted:
                        assignments.append(quoted.group('value'))
                    env_assignment = ENV_ASSIGNMENT_PATTERN.search(line)
                    if env_assignment:
                        assignments.append(env_assignment.group(1))
                    for value in assignments:
                        if not self._placeholder(value) and self._looks_sensitive_literal(value):
                            findings.append(
                                self._finding(path, line_number, 'secret_assignment', value)
                            )
        return {'ok': not findings, 'scanned_files': scanned, 'findings': findings}

    def repository_paths(self) -> list[Path]:
        process = subprocess.run(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        paths = []
        for item in process.stdout.split(b'\x00'):
            if not item:
                continue
            path = self.root / item.decode('utf-8', errors='surrogateescape')
            if not any(part in EXCLUDED_PARTS for part in path.relative_to(self.root).parts):
                paths.append(path)
        return paths

    def scan_repository(self) -> dict[str, object]:
        return self.scan_paths(self.repository_paths())


__all__ = ['SecretScanner']

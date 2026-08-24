from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import requests

from core.content_sanitizer import ExternalContentSanitizer


def _normalize_result_url(value: str) -> str:
    raw = str(value or '').strip()
    if raw.startswith('//'):
        raw = f'https:{raw}'
    parsed = urllib_parse.urlparse(raw)
    if parsed.netloc.lower().endswith('duckduckgo.com') and parsed.path == '/l/':
        target = (urllib_parse.parse_qs(parsed.query).get('uddg') or [''])[0]
        parsed = urllib_parse.urlparse(target)
        raw = target
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return ''
    return raw


class _DuckDuckGoParser(HTMLParser):
    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture = ''

    @staticmethod
    def _classes(attributes: list[tuple[str, str | None]]) -> set[str]:
        values = dict(attributes).get('class') or ''
        return {item for item in values.split() if item}

    def _finish(self) -> None:
        if self.current and self.current.get('title') and self.current.get('url'):
            self.results.append(self.current)
        self.current = None
        self.capture = ''

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attributes)
        values = dict(attributes)
        if 'result__a' in classes:
            if self.current:
                self._finish()
            self.current = {
                'title': '',
                'url': _normalize_result_url(values.get('href') or ''),
                'snippet': '',
            }
            self.capture = 'title'
        elif self.current and 'result__snippet' in classes:
            self.capture = 'snippet'

    def handle_data(self, data: str) -> None:
        if not self.current or self.capture not in {'title', 'snippet'}:
            return
        value = ' '.join(str(data or '').split())
        if not value:
            return
        existing = self.current[self.capture]
        self.current[self.capture] = f'{existing} {value}'.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag not in {'a', 'div', 'span'}:
            return
        if self.capture == 'snippet':
            self._finish()
        else:
            self.capture = ''

    def close(self) -> None:
        super().close()
        if self.current and len(self.results) < self.limit:
            self._finish()
        self.results = self.results[: self.limit]


class _BodyResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self) -> '_BodyResponse':
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


def _browser_compatible_open(request: urllib_request.Request, timeout: float) -> _BodyResponse:
    response = requests.get(
        request.full_url,
        headers={
            'Accept': request.get_header('Accept') or 'text/html,application/xhtml+xml',
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 TrevorSearch/1.0'
            ),
        },
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    return _BodyResponse(bytes(response.content))


class WebSearchAdapter:
    def __init__(
        self,
        *,
        endpoint: str = 'https://html.duckduckgo.com/html/',
        enabled: bool = True,
        timeout: float = 10.0,
        opener: Callable[..., Any] | None = None,
        sanitizer: ExternalContentSanitizer | None = None,
    ) -> None:
        self.endpoint = str(endpoint or '').strip()
        self.enabled = bool(enabled)
        self.timeout = max(2.0, min(float(timeout), 20.0))
        self.opener = opener or _browser_compatible_open
        self.sanitizer = sanitizer or ExternalContentSanitizer()

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.endpoint.startswith('https://'))

    def search(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 10))
        sanitized = self.sanitizer.sanitize(message=query)
        safe_query = str(sanitized.payload.get('message') or '').strip()
        if not self.available:
            return {'ok': False, 'error': 'search_not_configured', 'results': []}
        if not safe_query:
            return {'ok': False, 'error': 'search_query_required', 'results': []}
        url = f'{self.endpoint}?{urllib_parse.urlencode({"q": safe_query})}'
        request = urllib_request.Request(
            url,
            headers={
                'Accept': 'text/html,application/xhtml+xml',
                'User-Agent': 'TrevorSearch/1.0 (+private-redacted-query)',
            },
            method='GET',
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = response.read()[: 2 * 1024 * 1024].decode('utf-8', errors='replace')
        except (
            OSError,
            requests.RequestException,
            urllib_error.HTTPError,
            urllib_error.URLError,
            TimeoutError,
        ):
            return {
                'ok': False,
                'error': 'search_unavailable',
                'query': safe_query,
                'results': [],
            }
        parser = _DuckDuckGoParser(safe_limit)
        parser.feed(body)
        parser.close()
        return {
            'ok': bool(parser.results),
            'query': safe_query,
            'source': 'duckduckgo_html',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'redaction_count': sanitized.redaction_count,
            'results': parser.results,
            'error': '' if parser.results else 'search_empty',
        }


__all__ = ['WebSearchAdapter']

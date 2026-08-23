from __future__ import annotations

import ipaddress
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urljoin, urlparse


class AIHordeAssetError(RuntimeError):
    pass


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AIHordeAssetStore:
    CONTENT_TYPES = {
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/webp': '.webp',
    }

    def __init__(
        self,
        data_root: str | Path,
        *,
        resolver: Callable[[str], list[str]] | None = None,
        fetcher: Callable[[str, int], Any] | None = None,
        max_bytes: int = 15 * 1024 * 1024,
        allow_test_networks: bool = False,
    ):
        self.asset_dir = Path(data_root).expanduser().resolve() / 'ai_horde' / 'assets'
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.resolver = resolver or self._resolve_host
        self.fetcher = fetcher or self._fetch_once
        self.max_bytes = max_bytes
        self.allow_test_networks = allow_test_networks
        self._assets: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _resolve_host(host: str) -> list[str]:
        return sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        )

    def _safe_ip(self, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        if self.allow_test_networks and address in ipaddress.ip_network('203.0.113.0/24'):
            return True
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )

    def _validate_url(self, url: str) -> set[str]:
        parsed = urlparse(str(url or ''))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise AIHordeAssetError('asset_fetch_failed')
        try:
            addresses = set(self.resolver(parsed.hostname))
        except Exception as exc:
            raise AIHordeAssetError('asset_fetch_failed') from exc
        if not addresses or any(not self._safe_ip(address) for address in addresses):
            raise AIHordeAssetError('asset_fetch_failed')
        return addresses

    @staticmethod
    def _peer_ip(response: Any) -> str:
        candidates = (
            getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None),
            getattr(getattr(response, 'fp', None), '_sock', None),
        )
        for candidate in candidates:
            if candidate is not None:
                try:
                    return str(candidate.getpeername()[0])
                except Exception:
                    continue
        raise AIHordeAssetError('asset_fetch_failed')

    def _fetch_once(self, url: str, limit: int) -> tuple[bytes, str, str, str]:
        opener = urllib_request.build_opener(_NoRedirect())
        request = urllib_request.Request(
            url,
            headers={'Accept': 'image/png,image/jpeg,image/webp', 'User-Agent': 'Trevor/1.0'},
        )
        try:
            with opener.open(request, timeout=30) as response:
                peer = self._peer_ip(response)
                content_type = str(response.headers.get_content_type()).lower()
                body = response.read(limit + 1)
                return body, content_type, peer, ''
        except urllib_error.HTTPError as exc:
            if int(exc.code) in {301, 302, 303, 307, 308}:
                return b'', '', '', str(exc.headers.get('Location', '') or '')
            raise AIHordeAssetError('asset_fetch_failed') from exc
        except (urllib_error.URLError, TimeoutError, socket.timeout) as exc:
            raise AIHordeAssetError('asset_fetch_failed') from exc

    @staticmethod
    def _valid_magic(body: bytes, content_type: str) -> bool:
        if content_type == 'image/png':
            return body.startswith(b'\x89PNG\r\n\x1a\n')
        if content_type == 'image/jpeg':
            return body.startswith(b'\xff\xd8\xff')
        if content_type == 'image/webp':
            return len(body) >= 12 and body[:4] == b'RIFF' and body[8:12] == b'WEBP'
        return False

    def save_remote(self, url: str) -> dict[str, Any]:
        current_url = str(url or '')
        for redirect_count in range(3):
            resolved = self._validate_url(current_url)
            fetched = self.fetcher(current_url, self.max_bytes)
            if not isinstance(fetched, tuple) or len(fetched) not in {3, 4}:
                raise AIHordeAssetError('asset_fetch_failed')
            body, content_type, peer_ip = fetched[:3]
            redirect = str(fetched[3] or '') if len(fetched) == 4 else ''
            if redirect:
                if redirect_count >= 2:
                    raise AIHordeAssetError('asset_fetch_failed')
                current_url = urljoin(current_url, redirect)
                continue
            if peer_ip not in resolved or not self._safe_ip(str(peer_ip)):
                raise AIHordeAssetError('asset_fetch_failed')
            normalized_type = str(content_type or '').split(';', 1)[0].strip().lower()
            if normalized_type not in self.CONTENT_TYPES:
                raise AIHordeAssetError('asset_fetch_failed')
            if not isinstance(body, bytes) or len(body) > self.max_bytes:
                raise AIHordeAssetError('asset_fetch_failed')
            if not self._valid_magic(body, normalized_type):
                raise AIHordeAssetError('asset_fetch_failed')
            asset_id = str(uuid.uuid4())
            path = self.asset_dir / f'{asset_id}{self.CONTENT_TYPES[normalized_type]}'
            temporary = path.with_name(f'{path.name}.tmp-{os.getpid()}')
            temporary.write_bytes(body)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            self._assets[asset_id] = {
                'path': path,
                'content_type': normalized_type,
                'created_at': time.time(),
            }
            return {
                'asset_id': asset_id,
                'url': f'/api/ai-horde/assets/{asset_id}',
                'alt': 'AI Horde 生成圖片',
            }
        raise AIHordeAssetError('asset_fetch_failed')

    def read_asset(self, asset_id: str) -> tuple[bytes, str] | None:
        try:
            normalized = str(uuid.UUID(str(asset_id)))
        except (ValueError, AttributeError, TypeError):
            return None
        record = self._assets.get(normalized)
        if not record or time.time() - float(record['created_at']) > 24 * 60 * 60:
            return None
        path = Path(record['path'])
        try:
            return path.read_bytes(), str(record['content_type'])
        except OSError:
            return None


__all__ = ['AIHordeAssetError', 'AIHordeAssetStore']

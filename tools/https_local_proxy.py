#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


class ProxyHandler(BaseHTTPRequestHandler):
    upstream_host: str = "127.0.0.1"
    upstream_port: int = 5002
    external_https_base: str = "https://127.0.0.1:5443"

    protocol_version = "HTTP/1.1"

    @classmethod
    def _rewrite_location(cls, value: str) -> str:
        """Rewrite localhost upstream redirects to external HTTPS base."""
        try:
            parsed = urlsplit(value)
        except Exception:
            return value
        if parsed.scheme not in {"http", "https"}:
            return value

        normalized_port = parsed.port
        if normalized_port not in {5001, 5002, cls.upstream_port}:
            return value

        base = urlsplit(cls.external_https_base.rstrip("/"))
        if not base.scheme or not base.netloc:
            return value
        return urlunsplit(
            (
                base.scheme,
                base.netloc,
                parsed.path or "/",
                parsed.query,
                parsed.fragment,
            )
        )

    def _proxy(self) -> None:
        body = b""
        length = self.headers.get("Content-Length")
        if length:
            try:
                body = self.rfile.read(int(length))
            except Exception:
                body = b""

        headers = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in HOP_BY_HOP_HEADERS:
                continue
            headers[k] = v
        # Preserve client-visible host so upstream redirects contain LAN host/IP.
        headers["Host"] = self.headers.get(
            "Host", f"{self.upstream_host}:{self.upstream_port}"
        )
        headers["X-Forwarded-Proto"] = "https"
        headers["X-Forwarded-For"] = self.client_address[0]

        conn = http.client.HTTPConnection(
            self.upstream_host, self.upstream_port, timeout=60
        )
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()

            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                lk = k.lower()
                if lk in HOP_BY_HOP_HEADERS:
                    continue
                if lk == "location":
                    v = self._rewrite_location(v)
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)
        except Exception as exc:
            payload = f"HTTPS proxy error: {exc}\n".encode("utf-8", errors="ignore")
            self.send_response(502, "Bad Gateway")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        finally:
            conn.close()

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy()

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Local HTTPS reverse proxy")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=5443)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=5002)
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    parser.add_argument("--external-https-base", default="")
    args = parser.parse_args()

    ProxyHandler.upstream_host = args.upstream_host
    ProxyHandler.upstream_port = args.upstream_port
    ProxyHandler.external_https_base = (
        args.external_https_base.strip()
        or f"https://127.0.0.1:{args.listen_port}"
    )

    httpd = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=args.certfile, keyfile=args.keyfile)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()

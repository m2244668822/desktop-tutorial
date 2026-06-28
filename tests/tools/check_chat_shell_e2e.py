#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_get(url: str, *, follow_redirects: bool = True):
    opener = (
        urllib.request.build_opener()
        if follow_redirects
        else urllib.request.build_opener(NoRedirect())
    )
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req, timeout=8) as resp:
            return (
                resp.status,
                dict(resp.headers.items()),
                resp.read().decode("utf-8", errors="ignore"),
            )
    except urllib.error.HTTPError as e:
        return (
            e.code,
            dict(e.headers.items()) if e.headers else {},
            e.read().decode("utf-8", errors="ignore"),
        )


def check(base_url: str) -> int:
    checks: list[tuple[str, bool, str]] = []

    status, _, body = http_get(f"{base_url}/health")
    health_ok = False
    try:
        health_ok = status == 200 and json.loads(body).get("ok") is True
    except Exception:
        health_ok = False
    checks.append(("GET /health returns ok=true", health_ok, f"status={status}"))

    status, headers, _ = http_get(f"{base_url}/", follow_redirects=False)
    location = headers.get("Location", "")
    checks.append(
        (
            "GET / redirects to /chat_shell",
            status in (301, 302, 307, 308) and location.endswith("/chat_shell"),
            f"status={status}, location={location}",
        )
    )

    status, _, body = http_get(f"{base_url}/chat_shell")
    checks.append(
        (
            "GET /chat_shell returns HTML",
            status == 200 and "<html" in body.lower(),
            f"status={status}",
        )
    )
    checks.append(
        (
            "chat_shell contains pywebview bridge call",
            "window.pywebview.api" in body,
            "missing bridge api marker",
        )
    )
    checks.append(
        (
            "chat_shell contains agent activity board",
            'id="agentActivityBoard"' in body and 'id="agentActivityMeta"' in body,
            "missing activity board markers",
        )
    )
    checks.append(
        (
            "chat_shell contains provider backoff contract",
            "PROVIDER_RATE_LIMIT_BACKOFF_MS" in body and 'let _tasksFilter = "unresolved";' in body,
            "missing backoff/filter contract",
        )
    )

    status, _, body = http_get(f"{base_url}/chat")
    checks.append(
        (
            "GET /chat remains available (compat)",
            status == 200 and "<html" in body.lower(),
            f"status={status}",
        )
    )

    status, _, body = http_get(f"{base_url}/api/get_status")
    api_ok = False
    try:
        payload = json.loads(body)
        api_ok = status == 200 and isinstance(payload, dict) and "monitoring" in payload
    except Exception:
        api_ok = False
    checks.append(
        ("GET /api/get_status returns monitoring payload", api_ok, f"status={status}")
    )

    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name} ({detail})")
        if not ok:
            failed += 1

    if failed:
        print(f"\nE2E failed: {failed} check(s) failed.")
        return 1
    print("\nE2E passed: all checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minimal E2E checks for chat_shell-first web mode."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:5001",
        help="Desktop web server base URL.",
    )
    args = parser.parse_args()
    return check(args.base_url.rstrip("/"))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OpenClaw gateway adapter used during the phased Perob takeover."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


class OpenClawAdapter:
    """Expose safe gateway health and optional HTTP task forwarding."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).expanduser().resolve()
        self.host = os.getenv("OPENCLAW_GATEWAY_HOST", "127.0.0.1").strip() or "127.0.0.1"
        self.port = int(os.getenv("OPENCLAW_GATEWAY_PORT", "18789") or 18789)
        self.token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip()
        self.task_endpoint = os.getenv("OPENCLAW_TASK_ENDPOINT", "").strip()
        self.enabled = os.getenv("OPENCLAW_ENABLED", "false").strip().lower() == "true"

    def _port_up(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=1.0):
                return True
        except OSError:
            return False

    def status(self) -> dict[str, Any]:
        port_up = self._port_up()
        ready = bool(self.enabled and port_up and self.token)
        return {
            "ok": ready,
            "enabled": self.enabled,
            "status": "connected" if ready else ("degraded" if self.enabled else "disabled"),
            "host": self.host,
            "port": self.port,
            "port_up": port_up,
            "token_configured": bool(self.token),
            "task_forwarding_configured": bool(self.task_endpoint),
            "lobster_requested": True,
            "checked_at": datetime.now().isoformat(),
        }

    def forward_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Forward only when an explicit HTTP adapter endpoint is configured."""
        if not self.enabled:
            return {"ok": False, "error": "openclaw_disabled"}
        if not self.token:
            return {"ok": False, "error": "openclaw_token_missing"}
        if not self.task_endpoint:
            return {"ok": False, "error": "openclaw_task_endpoint_missing"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            self.task_endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
                return {"ok": True, "response": data}
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": "openclaw_forward_failed", "detail": str(exc)}


__all__ = ["OpenClawAdapter"]

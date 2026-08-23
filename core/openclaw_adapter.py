#!/usr/bin/env python3
"""OpenClaw gateway adapter used during the phased Perob takeover."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import uuid
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
        token_file = Path(
            os.getenv(
                "OPENCLAW_GATEWAY_TOKEN_FILE",
                str(Path.home() / ".openclaw" / "perob-gateway-token"),
            )
        ).expanduser()
        self.token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip()
        if not self.token and token_file.is_file():
            try:
                self.token = token_file.read_text(encoding="utf-8").strip()
            except OSError:
                self.token = ""
        self.task_endpoint = os.getenv("OPENCLAW_TASK_ENDPOINT", "").strip()
        self.enabled = os.getenv("OPENCLAW_ENABLED", "false").strip().lower() == "true"
        self.takeover_mode = (
            os.getenv("OPENCLAW_TAKEOVER_MODE", "execution_only").strip()
            or "execution_only"
        )
        self.last_forward_at = ""
        self.last_forward_error = ""
        self.last_readable_response = False

    def _openclaw_bin(self) -> str:
        configured = os.getenv("OPENCLAW_BIN", "").strip()
        candidates = [
            configured,
            shutil.which("openclaw") or "",
            "/usr/local/bin/openclaw",
            "/opt/homebrew/bin/openclaw",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return candidate
        return ""

    def _port_up(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=1.0):
                return True
        except OSError:
            return False

    def status(self) -> dict[str, Any]:
        port_up = self._port_up()
        ready = bool(self.enabled and port_up and self.token)
        openclaw_bin = self._openclaw_bin()
        websocket_available = bool(ready and not self.task_endpoint)
        if self.task_endpoint:
            forwarding_mode = "http"
        elif websocket_available:
            forwarding_mode = "websocket"
        elif self.enabled:
            forwarding_mode = "unavailable"
        else:
            forwarding_mode = "disabled"
        return {
            "ok": ready,
            "enabled": self.enabled,
            "status": "connected" if ready else ("degraded" if self.enabled else "disabled"),
            "host": self.host,
            "port": self.port,
            "port_up": port_up,
            "token_configured": bool(self.token),
            "task_forwarding_configured": bool(self.task_endpoint or websocket_available),
            "cli_forwarding_available": bool(ready and openclaw_bin),
            "cli_path": openclaw_bin,
            "websocket_forwarding_available": websocket_available,
            "forwarding_mode": forwarding_mode,
            "takeover_mode": self.takeover_mode,
            "last_forward_at": self.last_forward_at,
            "last_forward_error": self.last_forward_error,
            "last_readable_response": self.last_readable_response,
            "lobster_requested": True,
            "checked_at": datetime.now().isoformat(),
        }

    def forward_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Forward through HTTP adapter when configured, otherwise through Gateway WebSocket."""
        if not self.enabled:
            return {"ok": False, "error": "openclaw_disabled"}
        if not self.token:
            return {"ok": False, "error": "openclaw_token_missing"}
        if self.task_endpoint:
            return self._forward_via_http(payload)
        if not self._port_up():
            return {"ok": False, "error": "openclaw_gateway_unreachable"}
        cli_result = self._forward_via_cli_agent(payload)
        if cli_result.get("ok"):
            return cli_result
        raw_result = self._forward_via_websocket(payload)
        if raw_result.get("ok"):
            return raw_result
        return self._remember_forward_result(
            {
                "ok": False,
                "error": "openclaw_forward_failed",
                "cli": cli_result,
                "websocket": raw_result,
            }
        )

    def _remember_forward_result(self, result: dict[str, Any]) -> dict[str, Any]:
        self.last_forward_at = datetime.now().isoformat()
        self.last_forward_error = "" if result.get("ok") else str(result.get("error", ""))
        self.last_readable_response = self._has_readable_response(result)
        return result

    @staticmethod
    def _has_readable_response(result: dict[str, Any]) -> bool:
        response = result.get("response", {}) if isinstance(result, dict) else {}
        if isinstance(response, str):
            return bool(response.strip())
        if not isinstance(response, dict):
            return False
        for key in ("content", "reply", "message", "text", "result"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return True
        payload = response.get("payload")
        if isinstance(payload, dict):
            for key in ("content", "reply", "message", "text", "result"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return True
        return False

    def _forward_via_http(self, payload: dict[str, Any]) -> dict[str, Any]:
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
                return self._remember_forward_result(
                    {"ok": True, "route": "openclaw_http", "response": data}
                )
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return self._remember_forward_result(
                {"ok": False, "error": "openclaw_forward_failed", "detail": str(exc)}
            )

    def _forward_via_cli_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Use the official OpenClaw Gateway CLI as the safest WebSocket client."""
        openclaw_bin = self._openclaw_bin()
        if not openclaw_bin:
            return {"ok": False, "error": "openclaw_cli_missing"}
        request_id = str(payload.get("id") or uuid.uuid4())
        params = {
            "message": str(payload.get("message", "") or ""),
            "timeout": int(payload.get("timeout", 30) or 30),
            "idempotencyKey": request_id,
            "sessionKey": str(
                payload.get("session_key")
                or os.getenv("OPENCLAW_SESSION_KEY", "perob-task-forwarding")
            ),
        }
        agent_id = payload.get("agent_id") or os.getenv("OPENCLAW_AGENT_ID", "")
        if agent_id:
            params["agentId"] = str(agent_id)
        cmd = [
            openclaw_bin,
            "gateway",
            "call",
            "agent",
            "--json",
            "--expect-final",
            "--timeout",
            str(max(15000, params["timeout"] * 1000 + 5000)),
            "--token",
            self.token,
            "--params",
            json.dumps(params, ensure_ascii=False),
        ]
        try:
            run_env = os.environ.copy()
            run_env["PATH"] = ":".join(
                part
                for part in [
                    "/usr/local/bin",
                    "/opt/homebrew/bin",
                    run_env.get("PATH", ""),
                ]
                if part
            )
            proc = subprocess.run(
                cmd,
                cwd=str(self.workspace),
                env=run_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(20, params["timeout"] + 10),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": "openclaw_cli_forward_failed", "detail": str(exc)}

        combined = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "openclaw_cli_forward_failed",
                "detail": combined[:1000],
                "returncode": proc.returncode,
            }
        try:
            response = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            response = {"content": proc.stdout.strip()}
        return self._remember_forward_result(
            {
                "ok": True,
                "route": "openclaw_websocket_cli",
                "id": request_id,
                "response": response,
            }
        )

    def _forward_via_websocket(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from websockets.sync.client import connect
        except Exception as exc:
            return self._remember_forward_result(
                {"ok": False, "error": "openclaw_websocket_unavailable", "detail": str(exc)}
            )

        request_id = str(payload.get("id") or uuid.uuid4())
        message = str(payload.get("message", "") or "")
        task_type = str(payload.get("task_type", "") or "").strip().lower()
        msg_type = "skill_invoke" if task_type in {"lobster", "skill_invoke"} else "chat"
        envelope = {
            "id": request_id,
            "type": msg_type,
            "payload": {
                "message": message,
                "role": payload.get("role", "工程師"),
                "mode": payload.get("mode", "execution"),
                "task_type": payload.get("task_type", "execution"),
                "require_approval": bool(payload.get("require_approval", False)),
                "workspace": str(self.workspace),
            },
        }
        url = f"ws://{self.host}:{self.port}?token={self.token}"
        try:
            with connect(url, open_timeout=5, close_timeout=2) as ws:
                ws.send(json.dumps(envelope, ensure_ascii=False))
                raw = ws.recv(timeout=15)
            try:
                response = json.loads(raw) if isinstance(raw, str) else {"raw": raw}
            except json.JSONDecodeError:
                response = {"content": str(raw)}
            if (
                isinstance(response, dict)
                and response.get("type") == "event"
                and str(response.get("event", "")).startswith("connect.")
            ):
                return {
                    "ok": False,
                    "error": "openclaw_handshake_not_completed",
                    "route": "openclaw_websocket",
                    "id": request_id,
                    "response": response,
                }
            return self._remember_forward_result(
                {
                    "ok": True,
                    "route": "openclaw_websocket",
                    "id": request_id,
                    "response": response,
                }
            )
        except Exception as exc:
            return self._remember_forward_result(
                {
                    "ok": False,
                    "error": "openclaw_websocket_forward_failed",
                    "detail": str(exc),
                }
            )


__all__ = ["OpenClawAdapter"]

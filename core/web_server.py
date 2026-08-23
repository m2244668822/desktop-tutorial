#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
?箄擃?Web 隡箸??冽芋蝯?(Web Server & API Handlers)
"""

from __future__ import annotations
import json
import os
import re
import errno
import socket
import threading
import time
import webbrowser
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode, parse_qs, urlparse

from core.api_auth import build_api_key_store
from core.agent_collaboration_audit import record_agent_collaboration_event
from core.ai_horde_assets import AIHordeAssetStore
from core.ai_horde_client import AIHordeClient, AIHordeError
from core.ai_horde_jobs import AIHordeJobManager
from core.audit_chain import HashChainAuditLog
from core.autonomy import AutonomyPolicy, AutonomyQueue, mark_user_activity
from core.capability_registry import build_capability_registry
from core.data_paths import ProjectPaths
from core.openclaw_adapter import OpenClawAdapter
from core.task_board import task_items_payload, task_summary_payload
from core.traffic_governor import decide_route
from core.trevor_identity import (
    CAPABILITY_MODES,
    TREVOR_AGENT_ID,
    TREVOR_DISPLAY_NAME,
    decorate_trevor_response,
    normalize_trevor_identity,
)

# Shim for pywebview API in web mode
WEB_BRIDGE_SHIM = r"""
<script>
(function () {
  async function callApi(path, payload) {
    const opts = { 
        method: payload ? "POST" : "GET", 
        headers: { "Content-Type": "application/json" },
        mode: 'cors'
    };
    if (payload) opts.body = JSON.stringify(payload);
    const resp = await fetch(path, opts);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return await resp.json();
  }
  window.pywebview = window.pywebview || {};
  window.pywebview.api = {
    get_status: () => callApi("/api/get_status"),
    get_api_onboarding_info: () => callApi("/api/get_api_onboarding_info"),
    open_external: (url) => callApi("/api/open_external", { url }),
    send_message: (message, role) => callApi("/api/send_message", { message, role }),
    rerun_workflow_step: (taskId, toolName, stepIndex) =>
      callApi("/api/rerun_workflow_step", { task_id: taskId, tool_name: toolName, step_index: stepIndex ?? -1 }),
  };
  const fireReady = () => window.dispatchEvent(new Event("pywebviewready"));
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fireReady, { once: true });
  } else {
    setTimeout(fireReady, 0);
  }
})();
</script>
"""

def inject_web_bridge_shim(html: str) -> str:
    """瘜典 JS Shim 隞交芋?祆??Ｘ??函?璈?啣?"""
    if "window.pywebview.api" in html and "pywebviewready" in html:
        return html
    if "</head>" in html:
        return html.replace("</head>", WEB_BRIDGE_SHIM + "\n</head>", 1)
    return WEB_BRIDGE_SHIM + "\n" + html


class WebServerMode:
    def __init__(self, bridge: any, workspace_path: Path, paths: ProjectPaths):
        self.bridge = bridge
        self.workspace_path = workspace_path
        self.paths = paths
        
        # Session & Snapshot Logic
        self._data_dir = self.paths.data
        self._conv_dir = self._data_dir / "conversations"
        self._conv_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir = self.paths.data / "archive" / "chat_sessions"
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        
        self._snapshot_lock = threading.Lock()
        self._snapshot_cache = {}
        self._snapshot_cache_ts = 0.0
        self._snapshot_ttl_sec = 1.2
        
        self._provider_lock = threading.Lock()
        self._provider_cache = {}
        self._provider_cache_ts = 0.0
        self._provider_ttl_sec = 2.0
        self.openclaw = OpenClawAdapter(self.workspace_path)
        self.ai_horde_client = AIHordeClient()
        self.ai_horde_assets = AIHordeAssetStore(self.paths.data)
        self.ai_horde_jobs = AIHordeJobManager(
            self.ai_horde_client,
            self.ai_horde_assets,
            max_concurrent=int(os.getenv("AI_HORDE_MAX_CONCURRENT_JOBS", "2") or "2"),
            max_queued=int(os.getenv("AI_HORDE_MAX_QUEUED_JOBS", "8") or "8"),
            timeout_seconds=float(os.getenv("AI_HORDE_JOB_TIMEOUT_SECONDS", "600") or "600"),
        )
        self.api_key_store, self.api_auth_status = build_api_key_store(self.paths.data)
        self.api_auth_required = str(
            os.getenv("TREVOR_API_AUTH_REQUIRED", "false") or "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.audit_log = HashChainAuditLog(self.paths.data / "audit" / "events.jsonl")
        self.autonomy_queue = AutonomyQueue(
            self.paths.data / "autonomy" / "task_queue.json"
        )

        self._agent_key_map = {"trevor": TREVOR_DISPLAY_NAME}
        self._openclaw_execution_tokens = {
            "修",
            "修復",
            "修正",
            "bug",
            "debug",
            "偵錯",
            "檢查",
            "驗證",
            "git",
            "push",
            "pull",
            "commit",
            "workflow",
            "server",
            "伺服器",
            "重啟",
            "啟動",
            "OpenClaw",
            "Lobster",
        }

    def authorize_headers(self, headers: any, required_scope: str) -> dict:
        if self.api_key_store is None:
            return {"ok": False, "error": "auth_not_configured"}
        authorization = str(headers.get("Authorization", "") or "").strip()
        supplied = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
        if not supplied:
            supplied = str(headers.get("X-API-Token", "") or "").strip()
        if not supplied:
            return {"ok": False, "error": "authentication_required"}
        return self.api_key_store.authenticate(supplied, required_scope=required_scope)

    def _normalize_route_path(self, path: str) -> str:
        """?舀 reverse-proxy 頝臬?憒?/Perob"""
        for prefix in ("/Perob", "/perob"):
            if path == prefix: return "/"
            if path.startswith(prefix + "/"):
                normalized = path[len(prefix):]
                return normalized if normalized.startswith("/") else "/" + normalized
        return path

    @staticmethod
    def _tcp_up(host: str, port: int, timeout: float = 0.8) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def readiness_payload(self) -> dict:
        bridge_ready = bool(getattr(self.bridge, "is_ready", False))
        knowledge_hub = self.bridge._knowledge_status_summary()
        memory_autosave = self.bridge.get_memory_autosave_status()
        aeg_training = self.bridge.get_aeg_training_status()
        openclaw = self.openclaw.status()
        tls_up = self._tcp_up("127.0.0.1", 5443)
        db_ready = bool(getattr(self.bridge, "memory_manager", None))
        required_ready = bool(bridge_ready and db_ready)
        degraded_reasons = []
        if not bool(knowledge_hub.get("faiss_ready")):
            degraded_reasons.append("faiss_not_ready")
        if not tls_up:
            degraded_reasons.append("tls_proxy_not_ready")
        if not openclaw.get("ok"):
            degraded_reasons.append("openclaw_not_ready")
        elif not openclaw.get("task_forwarding_configured"):
            degraded_reasons.append("openclaw_forwarding_degraded")
        if not aeg_training.get("ok"):
            degraded_reasons.append("aeg_training_not_ready")
        n8n_up = self._tcp_up("127.0.0.1", 5678)
        optional_services = {
            "n8n": {
                "up": n8n_up,
                "port": 5678,
                "required": False,
                "degrades_core_chat": False,
            }
        }
        try:
            provider_payload = (self.bridge.get_api_onboarding_info() or {}).get("providers", {})
        except Exception:
            provider_payload = {}
        capability_registry = build_capability_registry(
            self.workspace_path,
            readiness={"optional_services": optional_services},
            openclaw_status=openclaw,
            knowledge_status=knowledge_hub,
            provider_status=provider_payload if isinstance(provider_payload, dict) else {},
        )
        return {
            "ok": required_ready,
            "status": "ready" if required_ready and not degraded_reasons else "degraded",
            "required_ready": required_ready,
            "bridge_ready": bridge_ready,
            "database_ready": db_ready,
            "knowledge_hub": knowledge_hub,
            "memory_autosave": memory_autosave,
            "aeg_training": aeg_training,
            "tls_proxy": {"up": tls_up, "port": 5443},
            "openclaw": openclaw,
            "optional_services": optional_services,
            "capability_registry": capability_registry,
            "degraded_reasons": degraded_reasons,
            "workspace": str(self.workspace_path),
        }

    def topology_payload(self) -> dict:
        readiness = self.readiness_payload()
        traffic_governor = decide_route(
            "一般對話健康檢查",
            mode="discussion",
            memory_signal={"confidence": "low", "exact_match": False, "source_count": 0},
            capability_registry=readiness.get("capability_registry", {}),
        )
        return {
            "ok": True,
            "entry": "https://perob.com:5443",
            "canonical_web": "http://127.0.0.1:5001",
            "services": {
                "perob": {"port": 5001, "required": True, "up": True},
                "tls_proxy": {"port": 5443, "required": True, **readiness["tls_proxy"]},
                "openclaw": {"port": 18789, "required": False, **readiness["openclaw"]},
                "n8n": {
                    "port": 5678,
                    "required": False,
                    "up": self._tcp_up("127.0.0.1", 5678),
                    "degrades_core_chat": False,
                },
                "ollama": {"port": 11434, "required": False, "up": self._tcp_up("127.0.0.1", 11434)},
            },
            "routing": [
                "browser -> tls_proxy:5443",
                "tls_proxy:5443 -> perob:5001",
                "perob:5001 -> openclaw:18789 (phased, optional)",
                "perob:5001 -> DesktopBridge (emergency fallback)",
            ],
            "readiness": readiness,
            "capability_registry": readiness.get("capability_registry", {}),
            "traffic_governor": traffic_governor,
        }

    def trevor_status_payload(self) -> dict:
        readiness = self.readiness_payload()
        try:
            graphiti_port = int(os.getenv("TREVOR_GRAPHITI_PORT", "8091") or "8091")
        except (TypeError, ValueError):
            graphiti_port = 8091
        migration_root = self.paths.data / "migrations"
        graphiti_migration_manifest = migration_root / "graphiti_manifest.json"
        device_migration_manifest = migration_root / "trevor_data_manifest.json"
        autonomy_dir = self.paths.data / "autonomy"

        def migration_manifest(path: Path) -> dict:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
            return payload if isinstance(payload, dict) else {}

        def runtime_state(name: str) -> dict:
            path = autonomy_dir / name
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
            heartbeat = str(state.get("heartbeat_at", "") or "")
            try:
                parsed = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds(),
                )
            except ValueError:
                age_seconds = None
            ready = bool(
                state.get("daemon_status") == "running"
                and age_seconds is not None
                and age_seconds <= 180
            )
            return {
                "ready": ready,
                "status": str(state.get("daemon_status", "not_running") or "not_running"),
                "mode": str(state.get("mode", "") or ""),
                "heartbeat_at": heartbeat,
            }

        scheduler = runtime_state("scheduler_state.json")
        worker = runtime_state("worker_state.json")
        combined = runtime_state("daemon_state.json")
        scheduler_ready = scheduler["ready"] or combined["ready"]
        worker_ready = worker["ready"] or combined["ready"]
        local_monitor_ready = bool(getattr(self.bridge, "monitor_active", False))
        device_migration = migration_manifest(device_migration_manifest)
        graphiti_migration = migration_manifest(graphiti_migration_manifest)
        device_migration_ready = bool(device_migration)
        graphiti_migration_ready = bool(graphiti_migration)
        if device_migration_ready and graphiti_migration_ready:
            migration_state = "ready"
        elif device_migration_ready:
            migration_state = "device_ready_graphiti_pending"
        elif graphiti_migration_ready:
            migration_state = "graphiti_ready_device_pending"
        else:
            migration_state = "pending"
        try:
            queued_tasks = self.autonomy_queue.tasks()
        except (RuntimeError, OSError, AttributeError):
            queued_tasks = []
        tailscale_socket = Path("/var/run/tailscale/tailscaled.sock")
        return {
            "ok": bool(readiness.get("required_ready")),
            "identity": normalize_trevor_identity().public_dict(),
            "frontend": {"ready": True, "entry": "/chat_shell"},
            "backend": {
                "ready": bool(readiness.get("bridge_ready")),
                "status": readiness.get("status", "degraded"),
            },
            "graphiti": {
                "ready": self._tcp_up("127.0.0.1", graphiti_port),
                "private": True,
            },
            "autonomy": {
                "ready": bool(
                    (scheduler_ready and worker_ready)
                    or combined["ready"]
                    or local_monitor_ready
                ),
                "scheduler": {**scheduler, "ready": scheduler_ready},
                "worker": {**worker, "ready": worker_ready},
                "combined": combined,
                "pending_tasks": sum(task.get("status") == "pending" for task in queued_tasks),
                "max_concurrent_tasks": 1,
            },
            "tailscale": {
                "private_only": True,
                "configured": bool(
                    os.getenv("TAILSCALE_HOSTNAME", "").strip() or tailscale_socket.exists()
                ),
            },
            "data_migration": {
                "manifest_ready": device_migration_ready and graphiti_migration_ready,
                "state": migration_state,
                "device": {
                    "ready": device_migration_ready,
                    "unique_turns": int(device_migration.get("unique_turns", 0) or 0),
                    "conversation_threads": int(
                        device_migration.get("conversation_threads", 0) or 0
                    ),
                    "encrypted": True,
                },
                "graphiti": {
                    "ready": graphiti_migration_ready,
                    "migrated_count": int(
                        graphiti_migration.get("migrated_count", 0) or 0
                    ),
                    "redacted": True,
                },
            },
            "degraded_reasons": list(readiness.get("degraded_reasons", [])),
        }

    def trevor_provider_payload(self) -> dict:
        try:
            payload = self.bridge.get_trevor_provider_status() or {}
        except Exception:
            payload = {"ok": False, "providers": []}
        return {
            **payload,
            "identity": {"id": TREVOR_AGENT_ID, "display_name": TREVOR_DISPLAY_NAME},
            "secrets_exposed": False,
        }

    def _should_try_openclaw_task(self, message: str, mode: str = "auto") -> bool:
        status = self.openclaw.status()
        if not status.get("ok") or not status.get("task_forwarding_configured"):
            return False
        takeover_mode = str(status.get("takeover_mode") or "execution_only").lower()
        if takeover_mode in {"off", "disabled", "false", "0"}:
            return False
        registry = build_capability_registry(
            self.workspace_path,
            readiness={"optional_services": {"n8n": {"up": self._tcp_up("127.0.0.1", 5678)}}},
            openclaw_status=status,
            knowledge_status={},
            provider_status={},
        )
        decision = decide_route(
            message,
            mode=("execution" if takeover_mode in {"all", "always"} else mode),
            memory_signal={"confidence": "low", "exact_match": False, "source_count": 0},
            capability_registry=registry,
        )
        return bool(decision.get("openclaw_allowed"))

    @staticmethod
    def _extract_openclaw_reply(result: dict) -> str:
        response = result.get("response", {}) if isinstance(result, dict) else {}
        if isinstance(response, dict):
            for key in ("content", "reply", "message", "text", "result"):
                value = response.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            payload = response.get("payload")
            if isinstance(payload, dict):
                for key in ("content", "reply", "message", "text", "result"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        if isinstance(response, str) and response.strip():
            return response.strip()
        return ""

    def _forward_openclaw_or_fallback(
        self,
        payload: dict,
        role_value: str,
        *,
        allow_fallback: bool,
    ) -> dict:
        message = str(payload.get("message", "") or "")
        requested_agent = str(payload.get("agent", "") or "").strip()
        requested_role = str(role_value or TREVOR_DISPLAY_NAME).strip()
        capability_mode = str(payload.get("capability_mode", "") or "")
        deliberation = str(payload.get("deliberation", "auto") or "auto")
        identity = normalize_trevor_identity(
            agent=requested_agent,
            role=requested_role,
            capability_mode=capability_mode,
        )
        openclaw_payload = {
            "message": message,
            "role": TREVOR_DISPLAY_NAME,
            "agent": TREVOR_AGENT_ID,
            "capability_mode": identity.capability_mode,
            "mode": payload.get("interaction_mode", payload.get("mode", "execution")),
            "task_type": payload.get("task_type", "execution"),
            "require_approval": bool(payload.get("require_approval", False)),
        }
        openclaw_result = self.openclaw.forward_task(openclaw_payload)
        route = str(openclaw_result.get("route", "openclaw"))
        reply = self._extract_openclaw_reply(openclaw_result)
        if openclaw_result.get("ok") and reply:
            audit = record_agent_collaboration_event(
                self.workspace_path,
                task_goal=message,
                agent=TREVOR_DISPLAY_NAME,
                route=route,
                decision="OpenClaw 接管任務",
                outcome="success",
                remedy="無需回退",
                score_delta=5,
                details={"openclaw": openclaw_result},
            )
            return decorate_trevor_response({
                "ok": True,
                "reply": reply,
                "route": route,
                "status": "openclaw_completed",
                "response": openclaw_result.get("response", {}),
                "fallback_used": False,
                "audit_id": audit["id"],
                "openclaw": openclaw_result,
                "deliberation": {
                    "mode": deliberation,
                    "status": "controller_only",
                    "providers": ["nvidia"],
                },
            }, requested_agent=requested_agent, requested_role=requested_role, capability_mode=identity.capability_mode)

        audit = record_agent_collaboration_event(
            self.workspace_path,
            task_goal=message,
            agent=TREVOR_DISPLAY_NAME,
            route=route,
            decision="OpenClaw 優先轉送",
            outcome="failed",
            remedy="回退 DesktopBridge" if allow_fallback else "未允許回退",
            score_delta=-3,
            details={"openclaw": openclaw_result},
        )
        if not allow_fallback:
            return decorate_trevor_response({
                "ok": False,
                "route": route,
                "status": "openclaw_failed",
                "response": openclaw_result,
                "fallback_used": False,
                "audit_id": audit["id"],
            }, requested_agent=requested_agent, requested_role=requested_role, capability_mode=identity.capability_mode)

        bridge_result = self.bridge.send_message(
            message,
            role_value,
            payload.get("session_id", ""),
            payload.get("model", "auto"),
            payload.get("interaction_mode", "auto"),
            capability_mode,
            deliberation,
        )
        if isinstance(bridge_result, dict):
            bridge_result["fallback_used"] = True
            bridge_result["openclaw"] = openclaw_result
            bridge_result["audit_id"] = audit["id"]
            bridge_result["route"] = "DesktopBridge"
            bridge_result["status"] = "fallback_completed"
            return bridge_result
        return decorate_trevor_response({
            "ok": True,
            "reply": str(bridge_result),
            "route": "DesktopBridge",
            "status": "fallback_completed",
            "fallback_used": True,
            "audit_id": audit["id"],
            "openclaw": openclaw_result,
        }, requested_agent=requested_agent, requested_role=requested_role, capability_mode=identity.capability_mode)

    def get_handler(self, template_map, redirect_map):
        server_instance = self
        
        class Handler(BaseHTTPRequestHandler):
            def _require_scope(self, scope: str) -> dict | None:
                authorization = server_instance.authorize_headers(self.headers, scope)
                if authorization.get("ok"):
                    return authorization
                error = str(authorization.get("error", "authentication_required"))
                if error == "auth_not_configured":
                    status = HTTPStatus.SERVICE_UNAVAILABLE
                elif error == "scope_denied":
                    status = HTTPStatus.FORBIDDEN
                else:
                    status = HTTPStatus.UNAUTHORIZED
                self._send_json({"ok": False, "error": error}, status=status)
                return None

            def _is_client_disconnect(self, exc: BaseException) -> bool:
                if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                    return True
                if isinstance(exc, OSError):
                    return getattr(exc, "errno", None) in {
                        errno.EPIPE,
                        errno.ECONNRESET,
                        errno.ENOTCONN,
                    }
                return False

            def _send_cors_headers(self):
                """?潮?CORS 璅隞交??file:// ?楊靘?隢?"""
                origin = self.headers.get("Origin") or "*"
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, X-API-Token, Authorization, X-Agent-Internal, X-Agent-Sender, X-External-Agent-Proxy, X-Execution-Mode",
                )
                self.send_header("Access-Control-Max-Age", "86400")

            def _send_json(self, payload: dict, status: int = HTTPStatus.OK):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                try:
                    self.send_response(status)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                except OSError as exc:
                    if not self._is_client_disconnect(exc):
                        raise

            def _send_text(self, text: str, content_type: str = "text/html; charset=utf-8", status: int = HTTPStatus.OK):
                data = text.encode("utf-8")
                try:
                    self.send_response(status)
                    self._send_cors_headers()
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(data)
                except OSError as exc:
                    if not self._is_client_disconnect(exc):
                        raise

            def _send_binary(
                self,
                body: bytes,
                content_type: str,
                *,
                status: int = HTTPStatus.OK,
                private_cache: bool = False,
            ):
                try:
                    self.send_response(status)
                    self._send_cors_headers()
                    self.send_header("Content-Type", content_type)
                    self.send_header("X-Content-Type-Options", "nosniff")
                    if private_cache:
                        self.send_header("Cache-Control", "private, max-age=3600")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                except OSError as exc:
                    if not self._is_client_disconnect(exc):
                        raise

            def _send_redirect(self, location: str, status: int = HTTPStatus.FOUND):
                try:
                    self.send_response(status)
                    self._send_cors_headers()
                    self.send_header("Location", location)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except OSError as exc:
                    if not self._is_client_disconnect(exc):
                        raise

            def do_OPTIONS(self):
                """?? CORS ?炎隢?"""
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                route_path = server_instance._normalize_route_path(parsed.path)
                query = parse_qs(parsed.query)
                
                if route_path in redirect_map:
                    self._send_redirect(redirect_map[route_path])
                    return
                
                if route_path in {"/health", "/health/live", "/api/ping", "/status"}:
                    self._send_json({"ok": True, "status": "connected", "workspace": str(server_instance.workspace_path)})
                    return

                if route_path == "/health/ready":
                    self._send_json(server_instance.readiness_payload())
                    return

                if route_path == "/api/runtime/topology":
                    self._send_json(server_instance.topology_payload())
                    return

                if route_path == "/api/trevor/status":
                    self._send_json(server_instance.trevor_status_payload())
                    return

                if route_path == "/api/trevor/providers":
                    self._send_json(server_instance.trevor_provider_payload())
                    return

                if route_path == "/api/trevor/tasks":
                    if self._require_scope("tasks") is None:
                        return
                    try:
                        limit = int((query.get("limit") or ["50"])[0] or 50)
                    except (TypeError, ValueError):
                        self._send_json(
                            {"ok": False, "error": "invalid_limit"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    self._send_json(
                        task_items_payload(
                            server_instance.workspace_path,
                            status=str((query.get("status") or [""])[0]),
                            limit=max(1, min(limit, 500)),
                            compact=True,
                        )
                    )
                    return

                if route_path == "/api/trevor/audit":
                    if self._require_scope("audit") is None:
                        return
                    try:
                        limit = int((query.get("limit") or ["100"])[0] or 100)
                        events = server_instance.audit_log.read(limit=limit)
                        verification = server_instance.audit_log.verify()
                    except (RuntimeError, ValueError):
                        self._send_json(
                            {"ok": False, "error": "audit_chain_invalid"},
                            status=HTTPStatus.CONFLICT,
                        )
                        return
                    self._send_json(
                        {"ok": True, "verification": verification, "events": events}
                    )
                    return

                if route_path == "/api/trevor/users/keys":
                    if self._require_scope("users") is None:
                        return
                    self._send_json(
                        {
                            "ok": True,
                            "keys": server_instance.api_key_store.list_public(),
                        }
                    )
                    return

                if route_path == "/api/trevor/memory/status":
                    if self._require_scope("memory") is None:
                        return
                    manager = getattr(server_instance.bridge, "memory_manager", None)
                    conversations = getattr(manager, "_conversations", {}) if manager else {}
                    self._send_json(
                        {
                            "ok": True,
                            "identity": normalize_trevor_identity().public_dict(),
                            "threads": len(conversations) if isinstance(conversations, dict) else 0,
                            "conflict_policy": "safety_then_source_priority_then_recency",
                            "encrypted_at_rest": bool(getattr(manager, "_json_store", None)),
                        }
                    )
                    return

                if route_path == "/api/ai-horde/status":
                    self._send_json(server_instance.ai_horde_client.public_status())
                    return

                if route_path.startswith("/api/ai-horde/jobs/"):
                    if server_instance.api_auth_required and self._require_scope("chat") is None:
                        return
                    job_id = route_path.rsplit("/", 1)[-1]
                    try:
                        self._send_json(server_instance.ai_horde_jobs.get_job(job_id))
                    except AIHordeError as exc:
                        self._send_json(
                            {"ok": False, "state": "failed", "error": exc.public_dict()},
                            status=HTTPStatus.NOT_FOUND
                            if exc.code == "job_not_found"
                            else HTTPStatus.BAD_REQUEST,
                        )
                    return

                if route_path.startswith("/api/ai-horde/assets/"):
                    if server_instance.api_auth_required and self._require_scope("chat") is None:
                        return
                    asset_id = route_path.rsplit("/", 1)[-1]
                    asset = server_instance.ai_horde_assets.read_asset(asset_id)
                    if asset is None:
                        self._send_text("Not Found", status=HTTPStatus.NOT_FOUND)
                    else:
                        body, content_type = asset
                        self._send_binary(body, content_type, private_cache=True)
                    return

                if route_path == "/api/openclaw/status":
                    status = server_instance.openclaw.status()
                    self._send_json(
                        {
                            "ok": status.get("ok", False),
                            "forwarding_mode": status.get("forwarding_mode", ""),
                            **status,
                        }
                    )
                    return

                if route_path in {"/api/gateway/policy", "/gateway/policy"}:
                    self._send_json(
                        {
                            "ok": True,
                            "mode": "single_entry_gateway",
                            "canonical_entry": "/chat_shell",
                            "canonical_port": 5001,
                            "api_aliases": [
                                "/chat/agent",
                                "/chat/agent/",
                                "/api/send_message",
                                "/api/send_message/",
                            ],
                            "prefix_compatibility": ["/Perob/*", "/perob/*"],
                            "n8n_expected_port": 5678,
                            "n8n_mode": "independent_watchdog",
                        }
                    )
                    return

                if route_path == "/api/diag":
                    mm = getattr(server_instance.bridge, "memory_manager", None)
                    conversations = getattr(mm, "_conversations", {}) if mm else {}
                    self._send_json(
                        {
                            "ok": True,
                            "generated_at": datetime.now().isoformat(),
                            "workspace": str(server_instance.workspace_path),
                            "bridge_ready": bool(getattr(server_instance.bridge, "is_ready", False)),
                            "monitor_active": bool(getattr(server_instance.bridge, "monitor_active", False)),
                            "history_threads": len(conversations) if isinstance(conversations, dict) else 0,
                            "knowledge_hub": server_instance.bridge._knowledge_status_summary(),
                            "agent_memory_aeg": server_instance.bridge.get_agent_memory_aeg_status(),
                            "templates_dir": str(server_instance.paths.templates),
                            "data_dir": str(server_instance.paths.data),
                        }
                    )
                    return

                if route_path == "/api/get_status":
                    monitor_payload = server_instance.bridge.get_status()
                    self._send_json({"ok": True, "reply_count": server_instance.bridge.reply_counter, "monitor": monitor_payload, "monitoring": monitor_payload})
                    return

                if route_path == "/api/get_api_onboarding_info":
                    self._send_json(server_instance.bridge.get_api_onboarding_info())
                    return

                if route_path in {"/api/providers/status", "/system/model-status"}:
                    try:
                        onboarding = server_instance.bridge.get_api_onboarding_info() or {}
                    except Exception:
                        onboarding = {}
                    providers_obj = onboarding.get("providers", onboarding) if isinstance(onboarding, dict) else {}
                    self._send_json(
                        {
                            "ok": True,
                            "providers": providers_obj if isinstance(providers_obj, dict) else {},
                            "key_state": onboarding.get("key_state", "") if isinstance(onboarding, dict) else "",
                            "model_state": onboarding.get("model_state", "") if isinstance(onboarding, dict) else "",
                            "base_url": onboarding.get("base_url", "") if isinstance(onboarding, dict) else "",
                        }
                    )
                    return

                if route_path in {"/api/n8n/status", "/system/communication/status", "/system/cns/status"}:
                    n8n_up = False
                    try:
                        with socket.create_connection(("127.0.0.1", 5678), timeout=1.5):
                            n8n_up = True
                    except Exception:
                        n8n_up = False
                    self._send_json(
                        {
                            "ok": True,
                            "status": "connected" if n8n_up else "degraded",
                            "n8n": {"up": n8n_up, "port": 5678},
                            "communication": {"up": True},
                            "cns": {"up": True},
                        }
                    )
                    return

                if route_path == "/agent/notifications":
                    self._send_json({"ok": True, "items": [], "unread": 0})
                    return

                if route_path == "/api/conversations":
                    # 與 /history 同步，避免前端顯示「未找到記錄」。
                    route_path = "/history"

                if route_path in {"/api/frontend/snapshot", "/api/frontend/snapshot/file"}:
                    provider_payload = {}
                    try:
                        status_payload = server_instance.bridge.get_status() or {}
                    except Exception:
                        status_payload = {}
                    try:
                        onboarding = server_instance.bridge.get_api_onboarding_info() or {}
                        candidate = onboarding.get("providers", onboarding)
                        if isinstance(candidate, dict):
                            provider_payload = candidate
                    except Exception:
                        provider_payload = {}
                    if not provider_payload:
                        provider_payload = {
                            "chat_preferred_provider": "nvidia",
                            "provider_catalog": [],
                            "nvidia": False,
                            "openai": False,
                            "gemini": False,
                            "groq": False,
                            "nvidia_key_configured": False,
                            "openai_key_configured": False,
                            "gemini_key_configured": False,
                            "groq_key_configured": False,
                        }
                    readiness_payload = server_instance.readiness_payload()
                    traffic_governor = decide_route(
                        "前端快照省流量政策",
                        mode="discussion",
                        memory_signal={"confidence": "low", "exact_match": False, "source_count": 0},
                        capability_registry=readiness_payload.get("capability_registry", {}),
                    )
                    self._send_json(
                        {
                            "ok": True,
                            "generated_at": datetime.now().isoformat(),
                            "workspace": str(server_instance.workspace_path),
                            "providers": provider_payload,
                            "capability_registry": readiness_payload.get("capability_registry", {}),
                            "traffic_governor": traffic_governor,
                            "learning": {
                                "ok": True,
                                "pending_goals": 0,
                                "recent_logs": [],
                            },
                            "tasks": {
                                "summary": task_summary_payload(server_instance.workspace_path),
                                "items": task_items_payload(
                                    server_instance.workspace_path,
                                    status="",
                                    limit=30,
                                    compact=True,
                                ).get("items", []),
                            },
                            "archive": {"items": []},
                            "communication": {"ok": True},
                            "monitor": status_payload,
                            "knowledge_hub": server_instance.bridge._knowledge_status_summary(),
                            "memory_autosave": server_instance.bridge.get_memory_autosave_status(),
                            "aeg_training": server_instance.bridge.get_aeg_training_status(),
                            "agent_memory_aeg": server_instance.bridge.get_agent_memory_aeg_status(),
                            "history_count": len(
                                getattr(getattr(server_instance.bridge, "memory_manager", None), "_conversations", {}) or {}
                            ),
                        }
                    )
                    return

                if route_path in {"/api/orchestrator/status", "/api/get_status"}:
                    self._send_json(
                        {
                            "ok": True,
                            "running": True,
                            "cycle_count": int(getattr(server_instance.bridge, "reply_counter", 0)),
                            "pending_goals": 0,
                            "last_cycle_at": datetime.now().isoformat(),
                            "kal_loop": {
                                "distiller_active": True,
                                "validator_active": True,
                                "brave_api": False,
                                "max_rounds_per_goal": 2,
                            },
                            "workflow": {},
                        }
                    )
                    return

                if route_path in {"/trace/learning-status"}:
                    self._send_json({"ok": True, "pending_goals": 0, "recent_logs": []})
                    return

                if route_path in {"/agent/tasks/summary", "/api/tasks/summary", "/trace/tasks"}:
                    self._send_json(task_summary_payload(server_instance.workspace_path))
                    return

                if route_path == "/agent/tasks":
                    qs = parse_qs(parsed.query or "")
                    try:
                        limit = int((qs.get("limit") or ["30"])[0] or 30)
                    except Exception:
                        limit = 30
                    status_filter = (qs.get("status") or [""])[0]
                    compact = (qs.get("compact") or [""])[0].lower() in {"1", "true", "yes", "on"}
                    self._send_json(
                        task_items_payload(
                            server_instance.workspace_path,
                            status=status_filter,
                            limit=limit,
                            compact=compact,
                        )
                    )
                    return

                if route_path == "/history":
                    limit = 120
                    try:
                        qs = parse_qs(parsed.query or "")
                        limit = int((qs.get("limit") or ["120"])[0] or 120)
                    except Exception:
                        limit = 120
                    mm = getattr(server_instance.bridge, "memory_manager", None)
                    rows: list[dict] = []
                    if mm is not None:
                        conversations = getattr(mm, "_conversations", {}) or {}
                        if isinstance(conversations, dict):
                            for conv_id, conv in conversations.items():
                                for m in conv.get("messages", []):
                                    metadata = m.get("metadata", {}) if isinstance(m, dict) else {}
                                    rows.append(
                                        {
                                            "conversation_id": conv_id,
                                            "agent": TREVOR_AGENT_ID,
                                            "agent_name": TREVOR_DISPLAY_NAME,
                                            "capability_mode": str(
                                                metadata.get("capability_mode", "general")
                                                or "general"
                                            ),
                                            "timestamp": m.get("timestamp", ""),
                                            "user": m.get("user", ""),
                                            "assistant": m.get("assistant", ""),
                                        }
                                    )
                    rows.sort(key=lambda x: str(x.get("timestamp", "")))
                    self._send_json(rows[-max(1, min(limit, 1000)):])
                    return

                if route_path == "/archive/list":
                    files = []
                    try:
                        p = server_instance.workspace_path / "archive" / "chat_sessions"
                        p.mkdir(parents=True, exist_ok=True)
                        for f in sorted(p.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                            files.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)})
                    except Exception:
                        pass
                    self._send_json({"files": files})
                    return

                # 模板頁
                target = template_map.get(route_path)
                if target and target.exists():
                    html = target.read_text(encoding="utf-8", errors="ignore")
                    self._send_text(inject_web_bridge_shim(html))
                    return
                
                # ????鞈?摮?
                name = Path(route_path.lstrip("/")).name
                if name:
                    candidate = (server_instance.paths.templates / name).resolve()
                    if candidate.exists() and candidate.is_file():
                        ctype = "text/plain"
                        if candidate.suffix == ".css": ctype = "text/css"
                        elif candidate.suffix == ".js": ctype = "application/javascript"
                        self._send_text(candidate.read_text(encoding="utf-8", errors="ignore"), content_type=ctype)
                        return

                self._send_text("Not Found", status=HTTPStatus.NOT_FOUND)

            def do_HEAD(self):
                """Reuse GET routing while suppressing the response body."""
                self.do_GET()

            def do_POST(self):
                parsed = urlparse(self.path)
                route_path = server_instance._normalize_route_path(parsed.path)
                try:
                    raw_len = int(self.headers.get("Content-Length", "0") or "0")
                except (TypeError, ValueError):
                    raw_len = 0
                if raw_len < 0 or raw_len > 64 * 1024:
                    self._send_json(
                        {
                            "ok": False,
                            "error": AIHordeError("invalid_request").public_dict(),
                        },
                        status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    )
                    return
                body = self.rfile.read(raw_len) if raw_len > 0 else b"{}"
                try:
                    payload = json.loads(body.decode("utf-8") or "{}")
                except Exception:
                    payload = {}

                if route_path == "/api/ai-horde/jobs":
                    if server_instance.api_auth_required and self._require_scope("chat") is None:
                        return
                    try:
                        result = server_instance.ai_horde_jobs.create_job(payload)
                    except AIHordeError as exc:
                        status = (
                            HTTPStatus.TOO_MANY_REQUESTS
                            if exc.code == "queue_full"
                            else HTTPStatus.BAD_REQUEST
                        )
                        self._send_json(
                            {"ok": False, "state": "failed", "error": exc.public_dict()},
                            status=status,
                        )
                        return
                    self._send_json(result, status=HTTPStatus.ACCEPTED)
                    return

                if route_path == "/api/trevor/tasks":
                    authorization = self._require_scope("tasks")
                    if authorization is None:
                        return
                    instruction = str(payload.get("input", "") or "").strip()
                    category = str(payload.get("category", "maintenance") or "maintenance").lower()
                    requested_mode = str(payload.get("capability_mode", "") or "").lower()
                    if not instruction:
                        self._send_json(
                            {"ok": False, "error": "task_input_required"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    if category not in AutonomyPolicy.ALLOWED_CATEGORIES:
                        self._send_json(
                            {"ok": False, "error": "invalid_category"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    if requested_mode and requested_mode not in CAPABILITY_MODES:
                        self._send_json(
                            {"ok": False, "error": "invalid_capability_mode"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    try:
                        priority = int(payload.get("priority", 5) or 5)
                    except (TypeError, ValueError):
                        self._send_json(
                            {"ok": False, "error": "invalid_priority"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    identity = normalize_trevor_identity(
                        agent=str(payload.get("agent", "") or ""),
                        role=str(payload.get("role", "") or ""),
                        capability_mode=requested_mode,
                    )
                    task = server_instance.autonomy_queue.enqueue(
                        instruction,
                        capability_mode=identity.capability_mode,
                        category=category,
                        priority=priority,
                        metadata={
                            "requested_by_key": authorization.get("key_id", ""),
                            "legacy_alias_normalized": identity.deprecated_alias,
                            "source_role": identity.source_alias,
                        },
                    )
                    server_instance.audit_log.append(
                        "autonomy_task_queued",
                        {
                            "task_id": task["id"],
                            "category": task["category"],
                            "capability_mode": task["capability_mode"],
                            "actor_key_id": authorization.get("key_id", ""),
                        },
                    )
                    self._send_json({"ok": True, "task": task}, status=HTTPStatus.ACCEPTED)
                    return

                if route_path == "/api/trevor/users/keys":
                    authorization = self._require_scope("users")
                    if authorization is None:
                        return
                    try:
                        created = server_instance.api_key_store.create(
                            str(payload.get("label", "api-client") or "api-client"),
                            payload.get("scopes", []),
                        )
                    except ValueError:
                        self._send_json(
                            {"ok": False, "error": "invalid_scope"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    server_instance.audit_log.append(
                        "user_key_created",
                        {
                            "actor_key_id": authorization.get("key_id", ""),
                            "created_key_id": created["record"]["id"],
                            "prefix": created["record"]["prefix"],
                            "scopes": created["record"]["scopes"],
                        },
                    )
                    self._send_json({"ok": True, **created}, status=HTTPStatus.CREATED)
                    return

                if route_path == "/api/trevor/users/keys/revoke":
                    authorization = self._require_scope("users")
                    if authorization is None:
                        return
                    key_id = str(payload.get("key_id", "") or "").strip()
                    if not server_instance.api_key_store.revoke(key_id):
                        self._send_json(
                            {"ok": False, "error": "key_not_found"},
                            status=HTTPStatus.NOT_FOUND,
                        )
                        return
                    server_instance.audit_log.append(
                        "user_key_revoked",
                        {
                            "actor_key_id": authorization.get("key_id", ""),
                            "revoked_key_id": key_id,
                        },
                    )
                    self._send_json({"ok": True, "key_id": key_id})
                    return

                if route_path in {"/api/send_message", "/api/send_message/", "/chat/agent", "/chat/agent/"}:
                    if server_instance.api_auth_required and self._require_scope("chat") is None:
                        return
                    mark_user_activity(server_instance.paths.data)
                    requested_agent = str(payload.get("agent", "") or "").strip()
                    role_value = payload.get("role") or requested_agent or TREVOR_DISPLAY_NAME
                    capability_mode = payload.get("capability_mode", "")
                    deliberation = payload.get("deliberation", "auto")
                    # 若 chat shell 傳 agent key，先轉成 bridge 需要的 role。
                    if route_path in {"/chat/agent", "/chat/agent/"}:
                        agent_to_role = {
                            "trevor": TREVOR_DISPLAY_NAME,
                            "dispatcher": "申言者",
                            "manager": "申言者",
                            "general": "通用",
                            "researcher": "研究員",
                            "engineer": "工程師",
                            "xiaobian": "小編",
                            "proclaimer": "申言者",
                            "prophet": "申言者",
                            "whitehat": "帽子",
                            "hat": "帽子",
                            "relay": "中繼器",
                        }
                        role_value = agent_to_role.get(
                            str(payload.get("agent", "")).strip().lower(),
                            role_value,
                        )
                    if server_instance._should_try_openclaw_task(
                        str(payload.get("message", "") or ""),
                        str(payload.get("interaction_mode", payload.get("mode", "auto"))),
                    ):
                        try:
                            self._send_json(
                                server_instance._forward_openclaw_or_fallback(
                                    payload,
                                    role_value,
                                    allow_fallback=True,
                                )
                            )
                            return
                        except Exception:
                            pass
                    try:
                        res = server_instance.bridge.send_message(
                            payload.get("message", ""),
                            role_value,
                            payload.get("session_id", ""),
                            payload.get("model", "auto"),
                            payload.get("interaction_mode", "auto"),
                            capability_mode,
                            deliberation,
                        )
                    except Exception as exc:
                        self._send_json(decorate_trevor_response(
                            {
                                "ok": False,
                                "error": "send_message_failed",
                                "detail": str(exc),
                            },
                            requested_agent=requested_agent,
                            requested_role=str(role_value),
                            capability_mode=str(capability_mode),
                        ),
                            status=HTTPStatus.INTERNAL_SERVER_ERROR,
                        )
                        return
                    self._send_json(res)
                    return

                if route_path == "/api/openclaw/task":
                    if server_instance.api_auth_required and self._require_scope("tasks") is None:
                        return
                    role_value = str(payload.get("role", "工程師") or "工程師")
                    self._send_json(
                        server_instance._forward_openclaw_or_fallback(
                            payload,
                            role_value,
                            allow_fallback=True,
                        )
                    )
                    return

                if route_path == "/api/upload_file":
                    self._send_json({"ok": False, "error": "upload_not_enabled_in_minimal_server"})
                    return

                if route_path == "/api/rerun_workflow_step":
                    try:
                        step_index = int(payload.get("step_index", -1))
                    except (TypeError, ValueError):
                        step_index = -1
                    result = server_instance.bridge.rerun_workflow_step(
                        str(payload.get("task_id", "")),
                        str(payload.get("tool_name", "")),
                        step_index,
                    )
                    self._send_json(result)
                    return

                if route_path in {"/archive/export"}:
                    self._send_json(
                        {
                            "ok": True,
                            "path": str(server_instance.workspace_path / "archive" / "chat_sessions"),
                            "count": 0,
                        }
                    )
                    return

                if route_path in {"/archive/cleanup"}:
                    keep_days = int(payload.get("keep_days", 30) or 30)
                    self._send_json({"ok": True, "removed": 0, "keep_days": keep_days})
                    return
                
                self._send_json({"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

            def log_message(self, format: str, *args):
                return # Quiet logs

        return Handler


def run_web_server(bridge: any, host: str, port: int, open_browser: bool = False) -> int:
    """Run Web server mode with shared bridge and template routes."""
    paths = ProjectPaths(bridge.workspace)
    server_logic = WebServerMode(bridge, bridge.workspace, paths)
    try:
        bridge.start_trevor_provider_validation()
    except Exception:
        pass
    
    template_map = {
        "/chat_shell": paths.templates / "chat_shell.html",
        "/agent_shell": paths.templates / "agent_shell.html",
        "/monitor_shell": paths.templates / "monitor_shell.html",
        "/chat": paths.templates / "chat.html",
    }
    redirect_map = {
        "/": "/chat_shell",
        "/index.html": "/chat_shell",
        "/chat": "/chat_shell",
        "/agent": "/agent_shell",
    }
    
    handler_class = server_logic.get_handler(template_map, redirect_map)
    server = ThreadingHTTPServer((host, port), handler_class)
    
    app_url = f"http://{host}:{port}/chat_shell"
    print(f"[web] server started at {app_url}")
    
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(app_url, new=2)).start()
        
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.monitor_active = False
        server.server_close()
    return 0

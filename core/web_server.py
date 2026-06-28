#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
?箄擃?Web 隡箸??冽芋蝯?(Web Server & API Handlers)
"""

from __future__ import annotations
import json
import os
import re
import threading
import time
import webbrowser
from copy import deepcopy
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode, parse_qs, urlparse

from core.data_paths import ProjectPaths
from core.task_board import task_items_payload, task_summary_payload

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
        self._archive_dir = self.paths.archive / "chat_sessions"
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        
        self._snapshot_lock = threading.Lock()
        self._snapshot_cache = {}
        self._snapshot_cache_ts = 0.0
        self._snapshot_ttl_sec = 1.2
        
        self._provider_lock = threading.Lock()
        self._provider_cache = {}
        self._provider_cache_ts = 0.0
        self._provider_ttl_sec = 2.0

        self._agent_key_map = {
            "general": "通用",
            "dispatcher": "申言者",
            "manager": "申言者",
            "researcher": "研究員",
            "engineer": "工程師",
            "relay": "中繼器",
            "xiaobian": "小編",
            "proclaimer": "申言者",
            "prophet": "申言者",
            "whitehat": "帽子",
            "hat": "帽子",
        }

    def _normalize_route_path(self, path: str) -> str:
        """?舀 reverse-proxy 頝臬?憒?/Perob"""
        for prefix in ("/Perob", "/perob"):
            if path == prefix: return "/"
            if path.startswith(prefix + "/"):
                normalized = path[len(prefix):]
                return normalized if normalized.startswith("/") else "/" + normalized
        return path

    def get_handler(self, template_map, redirect_map):
        server_instance = self
        
        class Handler(BaseHTTPRequestHandler):
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
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_text(self, text: str, content_type: str = "text/html; charset=utf-8", status: int = HTTPStatus.OK):
                data = text.encode("utf-8")
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_redirect(self, location: str, status: int = HTTPStatus.FOUND):
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

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
                
                if route_path in {"/health", "/api/ping", "/status"}:
                    self._send_json({"ok": True, "status": "connected", "workspace": str(server_instance.workspace_path)})
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
                    self._send_json(
                        {
                            "ok": True,
                            "generated_at": datetime.now().isoformat(),
                            "workspace": str(server_instance.workspace_path),
                            "providers": provider_payload,
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
                                agent_name = str(conv.get("agent_name", "通用") or "通用")
                                agent_key_map = {
                                    "總管": "proclaimer",
                                    "研究員": "researcher",
                                    "工程師": "engineer",
                                    "小編": "xiaobian",
                                    "申言者": "proclaimer",
                                    "帽子": "whitehat",
                                    "中繼器": "relay",
                                    "通用": "general",
                                }
                                agent = agent_key_map.get(agent_name, "general")
                                for m in conv.get("messages", []):
                                    rows.append(
                                        {
                                            "conversation_id": conv_id,
                                            "agent": agent,
                                            "agent_name": agent_name,
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

            def do_POST(self):
                parsed = urlparse(self.path)
                route_path = server_instance._normalize_route_path(parsed.path)
                raw_len = int(self.headers.get("Content-Length", "0") or "0")
                body = self.rfile.read(raw_len) if raw_len > 0 else b"{}"
                try:
                    payload = json.loads(body.decode("utf-8") or "{}")
                except Exception:
                    payload = {}

                if route_path in {"/api/send_message", "/api/send_message/", "/chat/agent", "/chat/agent/"}:
                    role_value = payload.get("role", "申言者")
                    # 若 chat shell 傳 agent key，先轉成 bridge 需要的 role。
                    if route_path in {"/chat/agent", "/chat/agent/"}:
                        agent_to_role = {
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
                    try:
                        res = server_instance.bridge.send_message(
                            payload.get("message", ""),
                            role_value,
                            payload.get("session_id", ""),
                            payload.get("model", "auto"),
                            payload.get("interaction_mode", "auto"),
                        )
                    except Exception as exc:
                        self._send_json(
                            {
                                "ok": False,
                                "error": "send_message_failed",
                                "detail": str(exc),
                                "role": role_value,
                            },
                            status=HTTPStatus.INTERNAL_SERVER_ERROR,
                        )
                        return
                    self._send_json(res)
                    return

                if route_path == "/api/upload_file":
                    self._send_json({"ok": False, "error": "upload_not_enabled_in_minimal_server"})
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
    
    template_map = {
        "/chat_shell": paths.templates / "chat.html",
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


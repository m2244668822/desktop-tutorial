#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體桌面應用程式 (Desktop Chat Application)
功能：
1. 提供 pywebview 桌面介面
2. 支援 Web 伺服器模式 (含 CORS 支援)
3. 智能體協調與訊息路由
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error as urllib_error
import urllib.request as urllib_request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from copy import deepcopy

try:
    import psutil
except Exception:
    psutil = None

from core.data_paths import ProjectPaths, resolve_data_root
from core.agent_prompts import (
    AGENT_SYSTEM_PROMPTS,
    AGENT_WINDOW_ROLES,
    ONLY_AGENT_ROLES,
    AGENT_PROFILE_DIRNAME,
    AGENT_PROFILE_FILES,
    GLOBAL_CHATGPT_PROMPT_FILE,
    SYNCED_CHATGPT_PROMPT_FILE,
    GLOBAL_CHATGPT_PROMPT_MAX_CHARS,
    get_agent_system_prompt
)

# 專案根（含本檔所在目錄）；可用環境變數 DESKTOP_CHAT_ROOT 覆寫
BASE_DIR = (
    Path(os.environ.get("DESKTOP_CHAT_ROOT", "")).expanduser().resolve()
    if os.environ.get("DESKTOP_CHAT_ROOT")
    else Path(__file__).resolve().parent
)
_tools_dir = BASE_DIR / "tools"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if _tools_dir.is_dir() and str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

# 初始化全局路徑管理
PATHS = ProjectPaths(BASE_DIR)

# 導入外部模組（帽子模組在專案根）
try:
    from 帽子_網路安全智能體 import HatCyberSecurityAgent
    HAT_AGENT_AVAILABLE = True
except ImportError:
    HAT_AGENT_AVAILABLE = False

try:
    from agent_memory_manager import AgentMemoryManager
except ImportError:
    AgentMemoryManager = None

try:
    from local_memory_api import LocalMemoryAPI
except ImportError:
    LocalMemoryAPI = None

try:
    from core.backend_router import allow_open_source_for_purpose, infer_backend_purpose
except Exception:
    allow_open_source_for_purpose = None
    infer_backend_purpose = None

try:
    from core.message_semantics import analyze_message
except Exception:
    analyze_message = None

try:
    from core.command_layer import dispatch_command
except Exception:
    dispatch_command = None

try:
    from core.knowledge_hub import KnowledgeHub
except Exception:
    KnowledgeHub = None

try:
    from core.llm_cns import (
        describe_key_state as cns_describe_key_state,
        frontend_provider_status as cns_frontend_provider_status,
        is_placeholder_value as cns_is_placeholder_value,
        llm_snapshot as cns_llm_snapshot,
        load_combined_env as cns_load_combined_env,
        provider_matrix as cns_provider_matrix,
        resolve_provider_config as cns_resolve_provider_config,
    )
except Exception:
    cns_describe_key_state = None
    cns_frontend_provider_status = None
    cns_is_placeholder_value = None
    cns_llm_snapshot = None
    cns_load_combined_env = None
    cns_provider_matrix = None
    cns_resolve_provider_config = None

CHAT_HTML = PATHS.templates / "chat.html"
CHAT_SHELL_HTML = PATHS.templates / "chat_shell.html"
MONITOR_SHELL_HTML = PATHS.templates / "monitor_shell.html"
AGENT_SHELL_HTML = PATHS.templates / "agent_shell.html"
RESEARCH_REPORT_MD = PATHS.reports / "open_source_agent_research_20260319.md"
_DEBUG_LOG_PATH = PATHS.root / ".cursor" / "debug-baa814.log"


def _agent_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    payload = {
        "sessionId": "baa814",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        req = urllib_request.Request(
            "http://127.0.0.1:7861/ingest/6fda4cc6-4fe0-4ab4-ab47-f4af6a90646c",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Debug-Session-Id": "baa814",
            },
            method="POST",
        )
        urllib_request.urlopen(req, timeout=1)
    except Exception:
        pass
    # endregion


def canonical_workspace_data_paths(workspace: Path) -> dict[str, str]:
    """與專案統一資料配置對齊的主路徑（供狀態 API / 除錯；以當前 workspace 為根）。"""
    paths = ProjectPaths(workspace)
    return {
        "main_conversations": str(paths.llama_data / "conversations.json"),
        "collaboration_context": str(paths.llama_logs / "collaboration_context.json"),
        "agent_memories": str(paths.data / "agent_memories"),
        "knowledge_hub_manifest": str(paths.knowledge_manifest),
        "chat_memory_config": str(paths.config / "chat_memory.json"),
        "security_knowledge_db": str(paths.data / "security_knowledge_db.json"),
        "open_source_catalog": str(paths.catalog_json),
    }


def run_web_server_mode(
    bridge: "DesktopBridge",
    workspace_path: Path,
    host: str,
    port: int,
    open_browser: bool,
) -> int:
    """與核心 Web 伺服器模組對接，支援 CORS 與全功能 API"""
    from core.web_server import run_web_server
    return run_web_server(bridge, host, port, open_browser)


# ====================== 智能體系統提示 ======================
# 通用規則：所有智能體均具備「巡查與溝通」能力。
# 1. 巡查：回覆前必須參考 [系統主動巡查快照]，若發現負載過高、API 異常或 Git 未提交，應主動提醒。
# 2. 溝通：若任務跨領域，應主動提及其他角色的專業建議（如研究員的資料、工程師的步驟）。

BACKEND_LABELS = {
    "nvidia": "NVIDIA/OpenAI-Compatible",
    "open_source": "Ollama/Open-Source",
    "offline": "Offline Fallback",
}

DEFAULT_CHAT_MODEL_BY_PROVIDER = {
    "nvidia": "meta/llama-3.1-8b-instruct",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",
    "gemini": "gemini-2.0-flash",
    "open_source": "qwen2.5:7b",
}


class DesktopBridge:
    """提供前端 JS 呼叫的橋接 API（多空間版本）"""

    def __init__(self, workspace: Path | None = None, energy_lite: bool = False):
        self.workspace = workspace or PATHS.root
        self.paths = ProjectPaths(self.workspace)
        self.energy_lite = bool(energy_lite)
        self.window = None
        self.chat_window = None
        self._webview_windows: list = []
        self.default_role = "總管"

        # 狀態變數
        self.last_message = ""
        self.last_message_ts = 0.0
        self.last_reply = ""
        self.monitor_seq = 0
        self.reply_history: list[tuple[str, float]] = []
        self.message_history: list[tuple[str, float]] = []
        self.conversation_context: list[dict] = []
        self.context_summary = ""
        self.reply_counter = 0
        self.last_diversified_reply = ""
        self.last_user_fingerprint = ""
        self.same_user_turn_count = 0
        self.max_reply_similarity = 0.88
        self.max_role_reply_history = 12
        self.role_reply_history: dict[str, list[str]] = {}
        self.promise_tracking: list[dict] = []
        self.last_message_analysis: dict = {}
        self.recent_message_analysis: list[dict] = []
        self.last_system_profile: dict = {}
        self.last_energy_decision: dict = {}
        self.connection_error_count = 0
        self.api_error_count = 0
        self.last_reminder_time = 0.0
        self.oss_is_healthy = False
        self.chat_mode = "online"
        self.offline_fallback_enabled = True
        self.max_history = 10
        self.max_reply_history = 250
        self.base_context_window = max(
            3, int(os.getenv("CHAT_BASE_CONTEXT_WINDOW", "4") or 4)
        )
        self.max_context = self.base_context_window
        self.max_context_upper = max(
            self.max_context, int(os.getenv("CHAT_MAX_CONTEXT_WINDOW", "8") or 8)
        )
        self.max_context_summary_length = 280
        self.workflow_fail_streak = 0
        self.auto_escalate_fail_streak = max(
            2, int(os.getenv("WORKFLOW_FAIL_ESCALATE_STREAK", "2") or 2)
        )
        self.high_risk_action_tokens = (
            "drop table",
            "delete from",
            "truncate",
            "rm -rf",
            "reset --hard",
            "覆蓋資料庫",
            "刪除資料",
            "清空資料",
        )
        self.last_error_type = ""
        self.last_error_time = 0
        self.reminder_interval = 60
        self.oss_health_check_interval = 30
        self.last_oss_health_check = 0
        self._status_cache = None
        self._status_cache_time = 0
        self._status_cache_ttl = 8 if self.energy_lite else 5
        self._available_models = None
        self._models_last_check = 0
        self.last_workflow_state: dict = {}
        self.force_cloud_offload = True
        self.energy_policy = {
            "cpu_high": 70,
            "cpu_critical": 85,
            "memory_high": 75,
            "memory_critical": 88,
        }
        self.enable_live_llm_default = (
            str(os.getenv("CHAT_LIVE_LLM_DEFAULT", "1")).strip().lower()
            not in {"0", "false", "off", "no"}
        )
        self.live_llm_timeout_sec = max(
            8.0, float(os.getenv("CHAT_LLM_TIMEOUT_SEC", "45") or 45)
        )
        self.live_llm_max_tokens = max(
            128, int(os.getenv("CHAT_LLM_MAX_TOKENS", "700") or 700)
        )
        self.live_llm_temperature = min(
            1.2, max(0.0, float(os.getenv("CHAT_LLM_TEMPERATURE", "0.45") or 0.45))
        )
        self.last_live_llm_meta: dict[str, Any] = {}
        self._langgraph_status_cache: dict[str, Any] = {
            "checked_at": 0.0,
            "available": False,
        }

        # 路徑跟隨 workspace（使用 centralized paths）
        self.env_file = self.paths.env_main
        self.env_candidates = self.paths.env_candidates
        self.catalog_json = self.paths.catalog_json
        self.relay_log = self.workspace / "logs" / "manager_relay_status.jsonl"
        self.interaction_graph_dir = self.paths.data / "interaction_graph"
        self.interaction_turn_log = self.interaction_graph_dir / "turn_index.jsonl"
        self.interaction_edge_log = self.interaction_graph_dir / "edges.jsonl"
        self.training_overlay_dir = self.paths.data / "training_overlay"
        self.training_turn_log = self.training_overlay_dir / "dialog_turns.jsonl"
        
        self.agent_system_prompts = dict(AGENT_SYSTEM_PROMPTS)
        self.agent_prompt_sources = {name: "builtin" for name in AGENT_SYSTEM_PROMPTS}
        self.agent_prompt_profiles: dict[str, dict] = {}
        self.agent_prompt_load_errors: dict[str, str] = {}
        self.global_agent_prompt = ""
        self.global_agent_prompt_source = ""
        
        self._refresh_agent_prompts()

        # 背景監控
        self.monitor_thread = None
        self.background_interval = 35 if self.energy_lite else 20
        self.monitor_active = True
        self.aeg_report_interval = 300 if self.energy_lite else 180
        self.last_aeg_report_ts = 0.0

        # 初始化各模組
        self._init_memory_manager()
        self._init_knowledge_hub()
        self.offline_replies = self._load_offline_replies()
        self.quick_replies = self._init_quick_replies()
        self.custom_replies: list[dict] = []
        self.agent_language_enabled = {
            "總管": True,
            "研究員": True,
            "工程師": True,
            "中繼器": True,
            "小編": True,
            "申言者": True,
            "帽子": HAT_AGENT_AVAILABLE,
        }

        self.hat_agent = HatCyberSecurityAgent() if HAT_AGENT_AVAILABLE else None
        self.agent_last_latency_ms = {name: 0 for name in self.agent_language_enabled}
        self.agent_last_error = {name: "" for name in self.agent_language_enabled}

        # 啟動背景監控
        self.start_background_monitor()
        self.is_ready = True

    def _refresh_agent_prompts(self):
        """刷新並整合所有提示詞"""
        from core.agent_prompts import load_global_agent_prompt, load_agent_prompt_profiles, get_agent_system_prompt
        self.global_agent_prompt = load_global_agent_prompt(self.workspace)
        self.agent_prompt_profiles = load_agent_prompt_profiles(self.workspace)
        
        for role in self.agent_system_prompts:
            self.agent_system_prompts[role] = get_agent_system_prompt(role, self.workspace)

    # ==================== 背景監控 ====================
    def start_background_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        self.monitor_thread = threading.Thread(
            target=self._background_monitor_loop,
            daemon=True,
            name=f"Monitor-{self.workspace.name}",
        )
        self.monitor_thread.start()
        print(
            f"✅ 空間 [{self.workspace.name}] 背景實時監控已啟動（每 {self.background_interval} 秒）"
        )

    def _background_monitor_loop(self):
        while True:
            if not self.monitor_active:
                time.sleep(10)
                continue
            try:
                time.sleep(self.background_interval)
                reminder = self._check_and_send_reminder(time.time())
                if reminder:
                    self._broadcast_reminder_js(reminder)
                self._refresh_aeg_shared_layers()
            except Exception as e:
                print(f"⚠️ 背景監控異常: {e}")
                time.sleep(5)

    def _refresh_aeg_shared_layers(self):
        now_ts = time.time()
        if now_ts - self.last_aeg_report_ts < self.aeg_report_interval:
            return
        self.last_aeg_report_ts = now_ts
        try:
            from core.workflow_runtime import build_tool_registry

            registry = build_tool_registry()
            aeg_spec = registry.get("aeg_keyword_graph")
            if aeg_spec:
                aeg_spec.handler(self.workspace, {"limit": 120})
        except Exception as exc:
            print(f"⚠️ AEG 關聯圖更新失敗: {exc}")
        try:
            cmd = [sys.executable, "tools/write_aeg_shared_report.py"]
            proc = subprocess.run(
                cmd,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                print(f"⚠️ AEG 報告更新失敗: rc={proc.returncode} {stderr}")
        except Exception as exc:
            print(f"⚠️ AEG 報告更新異常: {exc}")

    def stop_background_monitor(self):
        self.monitor_active = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            print(f"⏹️ 空間 [{self.workspace.name}] 背景監控已停止")

    def _init_memory_manager(self):
        """初始化智能體記憶管理系統"""
        self.memory_manager = None
        self.long_term_memory_api = None
        if AgentMemoryManager:
            try:
                self.memory_manager = AgentMemoryManager(
                    str(self.workspace), auto_save=True
                )
                # 嘗試加載已保存的對話上下文
                saved_context = self.memory_manager.get_conversation_history(
                    agent_name=self.default_role, limit=5
                )
                if saved_context:
                    print(f"   💾 已恢復 {len(saved_context)} 條對話記錄")
                # 保存初始IDE上下文
                vscode_status = self._vscode_status()
                self.memory_manager.save_ide_context(
                    {
                        "workspace": str(self.workspace),
                        "vscode": vscode_status,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception as e:
                print(f"   ⚠️ 記憶管理系統初始化失敗: {e}")
        if LocalMemoryAPI:
            try:
                self.long_term_memory_api = LocalMemoryAPI(str(self.workspace))
            except Exception as e:
                print(f"   ⚠️ 長期記憶系統初始化失敗: {e}")

    def _init_knowledge_hub(self):
        self.knowledge_hub = None
        if not KnowledgeHub:
            return
        try:
            self.knowledge_hub = KnowledgeHub(self.workspace)
            status = self.knowledge_hub.status()
            print(
                f"✅ Knowledge Hub 已初始化（items={status.get('total_items', 0)}, faiss={'on' if status.get('faiss_ready') else 'off'}）"
            )
        except Exception as exc:
            print(f"   ⚠️ Knowledge Hub 初始化失敗: {exc}")

    def _knowledge_status(self) -> dict:
        if not self.knowledge_hub:
            return {"ok": False, "error": "knowledge_hub_unavailable"}
        try:
            return self.knowledge_hub.status()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _knowledge_status_summary(self) -> dict:
        status = self._knowledge_status()
        if not status.get("ok"):
            return {
                "ok": False,
                "state": "unavailable",
                "total_items": 0,
                "faiss_ready": False,
                "last_error": status.get("error", ""),
            }
        return {
            "ok": True,
            "state": "ready" if status.get("faiss_ready") else "sqlite_only",
            "total_items": int(status.get("total_items", 0) or 0),
            "sqlite_ready": bool(status.get("sqlite_ready")),
            "faiss_ready": bool(status.get("faiss_ready")),
            "chatgpt_database_ready": bool(status.get("chatgpt_database_ready")),
            "chatgpt_database_path": status.get("chatgpt_database_path", ""),
            "manifest_path": status.get("manifest_path", ""),
            "manifest_exists": bool(status.get("manifest_exists")),
            "last_rebuild_at": status.get("last_rebuild_at", ""),
            "last_error": status.get("last_error", ""),
        }

    def _knowledge_search(self, query: str, top_k: int = 5) -> dict:
        if not self.knowledge_hub:
            return {"ok": False, "error": "knowledge_hub_unavailable", "matches": []}
        try:
            return self.knowledge_hub.search(query, top_k=top_k)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "matches": []}

    def _knowledge_rebuild(self) -> dict:
        if not self.knowledge_hub:
            return {"ok": False, "error": "knowledge_hub_unavailable", "rebuilt": False}
        try:
            return self.knowledge_hub.rebuild()
        except Exception as exc:
            return {"ok": False, "error": str(exc), "rebuilt": False}

    def _harmony_report_candidates(self) -> list[Path]:
        return [
            self.workspace / "reports" / "harmony_check_latest.json",
            self.workspace / "reports" / "harmony_check_mac_latest.json",
            self.workspace / "reports" / "harmony_check_windows_latest.json",
        ]

    def _harmony_status(self) -> dict:
        for report in self._harmony_report_candidates():
            if not report.exists():
                continue
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                payload["report_path"] = str(report)
                payload["report_mtime"] = datetime.fromtimestamp(
                    report.stat().st_mtime
                ).isoformat()
                return payload
            except Exception as exc:
                return {"ok": False, "error": f"harmony_report_parse_failed: {exc}"}
        return {"ok": False, "error": "harmony_report_missing"}

    def _harmony_status_summary(self) -> dict:
        status = self._harmony_status()
        if not status.get("overall_ok"):
            return {
                "ok": bool(status.get("ok", False)),
                "overall_ok": False,
                "state": "degraded",
                "report_path": status.get("report_path", ""),
                "timestamp": status.get("timestamp", ""),
                "error": status.get("error", ""),
            }
        checks = status.get("checks", []) if isinstance(status.get("checks"), list) else []
        failed = [item.get("name", "") for item in checks if not bool(item.get("ok", True))]
        return {
            "ok": True,
            "overall_ok": True,
            "state": "ready",
            "failed_checks": failed,
            "report_path": status.get("report_path", ""),
            "timestamp": status.get("timestamp", ""),
        }

    def _long_term_memory_top_k(self, user_message: str) -> int:
        text = (user_message or "").strip()
        base = 4
        if len(text) > 120:
            base = 6
        elif len(text) > 80:
            base = 5
        if self.same_user_turn_count >= 1:
            base += 1
        if any(
            token in text.lower()
            for token in ["api", "langgraph", "memory", "context", "workflow", "debug"]
        ):
            base += 1
        return max(3, min(base, 8))

    def _search_long_term_memory(self, query: str, top_k: int) -> list[dict]:
        if not self.long_term_memory_api or not query.strip():
            return []
        try:
            return self.long_term_memory_api.search_long_term_memory(query, top_k=top_k)
        except Exception:
            return []

    def _build_long_term_memory_block(
        self, query: str, top_k: int | None = None, max_chars: int = 800
    ) -> str:
        selected_k = top_k or self._long_term_memory_top_k(query)
        
        # 優先使用 KnowledgeHub 搜索，因為它已整合 GPT 歷史與本地知識
        matches = []
        if self.knowledge_hub:
            try:
                search_res = self.knowledge_hub.search(query, top_k=selected_k)
                if search_res.get("ok"):
                    matches = search_res.get("matches", [])
            except Exception:
                pass
        
        # Fallback to LocalMemoryAPI if KnowledgeHub failed or returned nothing
        if not matches and self.long_term_memory_api:
            matches = self._search_long_term_memory(query, selected_k)
            
        if not matches:
            return ""

        lines = ["[長期記憶與知識中樞檢索]"]
        used_chars = len(lines[0])
        for idx, item in enumerate(matches[:selected_k], start=1):
            source = item.get("source", "unknown")
            # 轉換來源名稱為更易讀的標籤
            source_label = {
                "gpt_history_user": "GPT對話(用戶)",
                "gpt_history_assistant": "GPT對話(助手)",
                "agent_memory_user": "智能體記錄(用戶)",
                "agent_memory_assistant": "智能體記錄(助手)",
                "chatgpt_local_knowledge": "本地知識庫",
            }.get(source, source)
            
            timestamp = str(item.get("timestamp", "") or "未知時間")[:19]
            summary = " ".join(str(item.get("summary", "")).split())
            if not summary:
                continue
            if self._is_stale_langgraph_unavailable_summary(summary):
                continue
                
            entry = f"{idx}. 【{source_label}】 {timestamp} | 摘要: {summary[:180]}"
            if used_chars + len(entry) > max_chars:
                break
            lines.append(entry)
            used_chars += len(entry)
            
        return "\n".join(lines) if len(lines) > 1 else ""

    def _dynamic_context_window(self, user_message: str = "") -> int:
        text = str(user_message or "").strip()
        window = self.base_context_window
        if len(text) > 90:
            window += 1
        if len(text) > 180:
            window += 1
        if self.same_user_turn_count >= 2:
            window += 1
        return max(self.base_context_window, min(window, self.max_context_upper))

    def _remember_dialog_turn(
        self, user_message: str, assistant_message: str, analysis: dict, workflow_ran: bool
    ) -> None:
        now = datetime.now().isoformat()
        user_text = str(user_message or "").strip()
        ai_text = str(assistant_message or "").strip()
        if user_text:
            self.conversation_context.append(
                {
                    "role": "user",
                    "content": user_text,
                    "timestamp": now,
                    "topic": str(analysis.get("primary_topic", "")) if isinstance(analysis, dict) else "",
                }
            )
        if ai_text:
            self.conversation_context.append(
                {
                    "role": "assistant",
                    "content": ai_text,
                    "timestamp": now,
                    "workflow_ran": bool(workflow_ran),
                }
            )
        hard_cap = max(24, self.max_context_upper * 10)
        if len(self.conversation_context) > hard_cap:
            trimmed = self.conversation_context[:-hard_cap]
            self.conversation_context = self.conversation_context[-hard_cap:]
            snippets = [
                str(item.get("content", "")).strip()
                for item in trimmed[-6:]
                if str(item.get("content", "")).strip()
            ]
            if snippets:
                self.context_summary = " | ".join(snippets)[: self.max_context_summary_length]

    def _append_jsonl(self, target: Path, payload: dict[str, Any]) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _normalize_keyword(self, value: str) -> str:
        token = re.sub(r"\s+", "", str(value or "").strip().lower())
        token = re.sub(r"[^\u4e00-\u9fffa-z0-9_#:+-]", "", token)
        return token[:32]

    def _langgraph_available_now(self, ttl_sec: float = 30.0) -> bool:
        now_ts = time.time()
        checked_at = float(self._langgraph_status_cache.get("checked_at", 0.0) or 0.0)
        if (now_ts - checked_at) <= max(1.0, float(ttl_sec)):
            return bool(self._langgraph_status_cache.get("available", False))
        available = False
        try:
            from core.langgraph_workflow import LANGGRAPH_AVAILABLE

            available = bool(LANGGRAPH_AVAILABLE)
        except Exception:
            available = False
        self._langgraph_status_cache = {"checked_at": now_ts, "available": available}
        return available

    def _is_stale_langgraph_unavailable_summary(self, summary: str) -> bool:
        text = str(summary or "")
        if not text:
            return False
        lower = text.lower()
        unavailable_markers = (
            "langgraph 尚未可用",
            "langgraph未可用",
            "langgraph not available",
            "回退到總管單一路由",
        )
        if not any(marker in text or marker in lower for marker in unavailable_markers):
            return False
        return self._langgraph_available_now(ttl_sec=30.0)

    def _derive_turn_keywords(self, message: str, analysis: dict, limit: int = 8) -> list[str]:
        text = str(message or "").strip()
        seed_words: list[str] = []
        if isinstance(analysis, dict):
            if analysis.get("primary_topic"):
                seed_words.append(str(analysis.get("primary_topic", "")))
            keywords = analysis.get("keywords", [])
            if isinstance(keywords, list):
                seed_words.extend(str(item) for item in keywords if item)

        # 從原句拆段，補強語義模組可能切得太碎的情況
        segments = re.split(r"[，,。！？!?；;、\n]", text)
        for seg in segments:
            seg = seg.strip()
            if seg:
                seed_words.append(seg)
        phrase_patterns = (
            "單一入口", "分支分流", "關係圖", "關鍵字檢索", "訓練分流",
            "智能體", "中樞系統", "前後端", "前端", "後端", "n8n", "git",
        )
        for phrase in phrase_patterns:
            if phrase.lower() in text.lower():
                seed_words.append(phrase)
        seed_words.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9_#:+-]{2,24}", text))

        stopwords = {
            "請", "幫我", "你", "我們", "這個", "那個", "一下", "可以", "需要",
            "然後", "就是", "是否", "問題", "今天", "現在", "剛剛", "不要", "重複",
            "生活化方式", "給我", "並給我", "請用", "解釋", "介紹", "說明",
        }
        domain_markers = (
            "入口", "分支", "智能體", "記憶", "關係圖", "訓練", "n8n", "git",
            "前端", "後端", "api", "檢索", "優化", "回覆", "工作流", "單一",
        )

        def cleanup(raw: str) -> str:
            token = self._normalize_keyword(raw)
            token = re.sub(r"^(請用|請幫我|請幫|請|幫我|給我|並給我|用)", "", token)
            token = re.sub(r"(方式|方法|步驟|一下|一下子|介紹|說明|解釋)$", "", token)
            token = token.strip()
            return token

        unique: dict[str, int] = {}
        for raw in seed_words:
            token = cleanup(raw)
            if not token or token in stopwords:
                continue
            if len(token) < 2 or len(token) > 12:
                continue
            score = len(token)
            for marker in domain_markers:
                if marker in token:
                    score += 20
            if token not in unique or score > unique[token]:
                unique[token] = score

        ranked = sorted(unique.items(), key=lambda kv: kv[1], reverse=True)
        result = [token for token, _ in ranked[:limit]]
        return result

    def _run_keyword_retrieval(self, keywords: list[str], per_keyword: int = 2) -> dict[str, Any]:
        checked = keywords[: max(1, min(6, len(keywords)))]
        payload: dict[str, Any] = {
            "ok": True,
            "engine": "knowledge_hub",
            "keywords": checked,
            "checked_count": len(checked),
            "matches": [],
        }
        if not checked:
            return payload
        if not self.knowledge_hub:
            payload["ok"] = False
            payload["error"] = "knowledge_hub_unavailable"
            return payload

        seen: set[tuple[str, str]] = set()
        matches: list[dict[str, Any]] = []
        for keyword in checked:
            try:
                res = self.knowledge_hub.search(keyword, top_k=per_keyword)
            except Exception:
                continue
            items = res.get("matches", []) if isinstance(res, dict) else []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                summary = " ".join(str(item.get("summary", "")).split())
                source = str(item.get("source", "") or "unknown")
                if not summary:
                    continue
                # 避免已過期的「LangGraph 不可用」歷史摘要污染目前判斷。
                if self._is_stale_langgraph_unavailable_summary(summary):
                    continue
                fp = (source, summary[:100])
                if fp in seen:
                    continue
                seen.add(fp)
                matches.append(
                    {
                        "keyword": keyword,
                        "source": source,
                        "timestamp": str(item.get("timestamp", "") or ""),
                        "summary": summary[:220],
                    }
                )
        payload["matches"] = matches[:12]
        payload["match_count"] = len(payload["matches"])
        return payload

    def _build_retrieval_brief(self, retrieval: dict[str, Any], max_items: int = 2) -> str:
        if not isinstance(retrieval, dict):
            return ""
        items = retrieval.get("matches", [])
        if not isinstance(items, list) or not items:
            return ""
        lines: list[str] = []
        for row in items[:max_items]:
            if not isinstance(row, dict):
                continue
            keyword = str(row.get("keyword", "")).strip()
            summary = str(row.get("summary", "")).strip()
            if not summary:
                continue
            if keyword:
                lines.append(f"{keyword}: {summary[:68]}")
            else:
                lines.append(summary[:68])
        return " | ".join(lines)[:220]

    def _record_turn_artifacts(
        self,
        session_id: str,
        role: str,
        user_message: str,
        assistant_message: str,
        analysis: dict,
        keywords: list[str],
        retrieval: dict[str, Any],
        workflow_ran: bool,
        backend: str,
        purpose: str,
        interaction_mode: str,
    ) -> None:
        now = datetime.now().isoformat()
        sid = str(session_id or "default")
        turn_id = f"{sid}#turn:{self.reply_counter}"
        topic = self._focus_topic(user_message, analysis if isinstance(analysis, dict) else {})
        turn_payload = {
            "timestamp": now,
            "turn_id": turn_id,
            "session_id": sid,
            "role": str(role or "總管"),
            "topic": topic,
            "keywords": keywords,
            "workflow_ran": bool(workflow_ran),
            "backend": backend,
            "purpose": purpose,
            "interaction_mode": interaction_mode,
            "user": str(user_message or "")[:400],
            "assistant": str(assistant_message or "")[:500],
            "retrieval_match_count": int(retrieval.get("match_count", 0) or 0)
            if isinstance(retrieval, dict)
            else 0,
        }
        self._append_jsonl(self.interaction_turn_log, turn_payload)

        for keyword in keywords[:8]:
            self._append_jsonl(
                self.interaction_edge_log,
                {
                    "timestamp": now,
                    "from": turn_id,
                    "to": f"kw:{keyword}",
                    "type": "mentions",
                    "weight": 1.0,
                },
            )
        if isinstance(retrieval, dict):
            for idx, item in enumerate(retrieval.get("matches", [])[:5], start=1):
                if not isinstance(item, dict):
                    continue
                source = self._normalize_keyword(item.get("source", "unknown"))
                summary = self._normalize_keyword(item.get("summary", ""))[:24]
                node = f"memory:{source}:{summary or idx}"
                self._append_jsonl(
                    self.interaction_edge_log,
                    {
                        "timestamp": now,
                        "from": turn_id,
                        "to": node,
                        "type": "retrieved_from",
                        "weight": 0.8,
                        "keyword": item.get("keyword", ""),
                    },
                )

    def _persist_training_overlay_sample(
        self,
        session_id: str,
        role: str,
        user_message: str,
        assistant_message: str,
        analysis: dict,
        keywords: list[str],
        workflow_ran: bool,
        backend: str,
    ) -> None:
        sample = {
            "timestamp": datetime.now().isoformat(),
            "session_id": str(session_id or "default"),
            "turn_id": f"{session_id or 'default'}#turn:{self.reply_counter}",
            "role": str(role or "總管"),
            "input": str(user_message or ""),
            "output": str(assistant_message or ""),
            "topic": self._focus_topic(user_message, analysis if isinstance(analysis, dict) else {}),
            "intent": str(analysis.get("intent", "")) if isinstance(analysis, dict) else "",
            "keywords": keywords,
            "workflow_ran": bool(workflow_ran),
            "backend": backend,
            "overlay_only": True,
            "label": "dialogue_training_sample",
        }
        self._append_jsonl(self.training_turn_log, sample)

    def _build_recent_context_block(self, user_message: str = "") -> str:
        context_info = ""
        depth = self._dynamic_context_window(user_message)
        if self.conversation_context:
            context_info = "\n\n最近對話上下文\n" + "\n".join(
                [
                    f"{'USER' if ctx.get('role') == 'user' else 'ASSISTANT'} {ctx.get('content', '')[:50]}"
                    for ctx in self.conversation_context[-depth:]
                ]
            )
        if self.context_summary:
            context_info += f"\n[壓縮歷史] {self.context_summary[:100]}"
        context_info += f"\n[對話序號] 回合 #{self.reply_counter} | depth={depth}"
        return context_info

    def _build_inspection_block(self) -> str:
        """主動巡查：彙整系統健康快照，供智能體主動感知環境。"""
        profile = self.last_system_profile or self._system_profile()
        git_summary = self._git_status_filtered(short=True) or "乾淨"
        api = self._api_health()
        
        lines = ["[系統主動巡查快照]"]
        lines.append(f"負載: CPU {profile.get('cpu_percent', 0):.1f}%, 記憶體 {profile.get('memory_percent', 0):.1f}%")
        lines.append(f"Git狀態: {git_summary.replace('\n', '; ')[:120]}")
        lines.append(f"API狀態: {api.get('key_source')}={api.get('key_state')}, 模型={api.get('model_state')}")
        
        if self.connection_error_count > 0 or self.api_error_count > 0:
            lines.append(f"異常統計: 連線錯誤 {self.connection_error_count} 次, API 錯誤 {self.api_error_count} 次")
        
        # 檢索存儲分層資訊 (如果 workflow 曾執行過)
        if self.last_workflow_state.get("task_state", {}).get("tool_outputs", {}).get("tiered_storage_health"):
            storage = self.last_workflow_state["task_state"]["tool_outputs"]["tiered_storage_health"]
            lines.append(f"存儲: {'SSD加速' if storage.get('ssd_mounted') else 'HDD降級'}")
            
        return "\n".join(lines)

    def _compose_model_message(
        self,
        agent_name: str,
        user_message: str,
        plan: str = "",
        workflow_memory_context: str = "",
    ) -> str:
        parts = [f"任務角色：{agent_name}", f"使用者訊息：{user_message}"]
        if plan:
            parts.append(f"執行計畫：{plan}")
        
        # 注入巡查快照，賦予智能體主動性
        parts.append(self._build_inspection_block())
        
        if workflow_memory_context:
            parts.append(workflow_memory_context.strip())
        semantic_block = self._build_semantic_context_block(user_message)
        if semantic_block:
            parts.append(semantic_block)
        memory_block = self._build_long_term_memory_block(user_message)
        if memory_block:
            parts.append(memory_block)
        recent_context = self._build_recent_context_block(user_message)
        if recent_context:
            parts.append(recent_context.strip())
        parts.append(
            "請優先根據當前需求回答，只有在長期記憶相關時才引用，避免重複與過度延伸。"
        )
        return "\n\n".join(part for part in parts if part)

    def _build_semantic_context_block(self, user_message: str) -> str:
        analysis = (
            self.last_message_analysis
            if self.last_message_analysis.get("text") == user_message
            else {}
        )
        if not analysis:
            return ""
        lines = ["[語義分析]"]
        if analysis.get("intent"):
            lines.append(f"意圖={analysis['intent']}")
        if analysis.get("primary_topic"):
            lines.append(f"主題={analysis['primary_topic']}")
        if analysis.get("keywords"):
            lines.append(f"關鍵詞={','.join(analysis['keywords'][:6])}")
        if analysis.get("domain_tags"):
            lines.append(f"領域標籤={','.join(analysis['domain_tags'][:4])}")
        return " | ".join(lines)

    def _fallback_message_analysis(self, text: str) -> dict:
        tokens = [
            t for t in re.split(r"[^\u4e00-\u9fffA-Za-z0-9]", text) if len(t) >= 2
        ]
        return {
            "text": text,
            "intent": "discussion",
            "primary_topic": tokens[0] if tokens else "一般對話",
            "keywords": tokens[:8],
            "domain_tags": ["general"],
            "role_hints": ["總管"],
        }

    def _role_to_agent_key(self, role: str) -> str:
        role_map = {
            "總管": "dispatcher",
            "通用": "general",
            "研究員": "researcher",
            "工程師": "engineer",
            "小編": "xiaobian",
            "申言者": "prophet",
            "帽子": "hat",
            "中繼器": "relay",
        }
        return role_map.get(str(role or "").strip(), "dispatcher")

    def _normalize_interaction_mode(self, mode: str | None) -> str:
        normalized = str(mode or "auto").strip().lower()
        return normalized if normalized else "auto"

    def _text_fingerprint(self, text: str) -> str:
        compact = re.sub(r"\s+", "", str(text or "").strip().lower())
        return re.sub(r"[^\u4e00-\u9fffa-z0-9]+", "", compact)[:240]

    def _pick_variant(self, options: list[str], seed_text: str = "") -> str:
        if not options:
            return ""
        idx = (self.reply_counter + len(seed_text or "")) % len(options)
        return options[idx]

    def _update_user_repeat_tracking(self, message: str) -> None:
        fingerprint = self._text_fingerprint(message)
        if fingerprint and fingerprint == self.last_user_fingerprint:
            self.same_user_turn_count = min(self.same_user_turn_count + 1, 6)
        else:
            self.same_user_turn_count = 0
        self.last_user_fingerprint = fingerprint

    def _remember_role_reply(self, role: str, reply: str) -> None:
        role_name = str(role or "總管")
        cleaned = str(reply or "").strip()
        if not cleaned:
            return
        history = self.role_reply_history.setdefault(role_name, [])
        history.append(cleaned)
        if len(history) > self.max_role_reply_history:
            del history[:-self.max_role_reply_history]

    def _is_reply_repetitive(self, role: str, candidate_reply: str) -> tuple[bool, float]:
        role_name = str(role or "總管")
        candidate_fp = self._text_fingerprint(candidate_reply)
        if not candidate_fp:
            return False, 0.0
        history = self.role_reply_history.get(role_name, [])
        if not history:
            return False, 0.0
        best = 0.0
        for prev in history[-5:]:
            ratio = difflib.SequenceMatcher(
                None, candidate_fp, self._text_fingerprint(prev)
            ).ratio()
            if ratio > best:
                best = ratio
        return best >= self.max_reply_similarity, best

    def _build_loop_breaker_reply(
        self, message: str, role: str, analysis: dict, similarity: float = 0.0
    ) -> str:
        role_name = role or "總管"
        focus = self._focus_topic(message, analysis)
        if (
            not self._has_system_objective_request(message)
            and not self._message_has_execution_intent(message)
        ):
            selected = self._build_general_non_system_reply(
                message=message,
                role=role_name,
                analysis=analysis,
                loop_breaking=True,
                retrieval_brief="",
            )
            if similarity >= self.max_reply_similarity:
                selected += f"\n（已避開近似回覆，上一輪相似度 {similarity:.2f}）"
            return selected

        variants = [
            f"【{role_name}】我知道你在追同一個重點「{focus}」。這次不重覆前一句，直接換成執行版：我先列問題假設、再列驗證步驟、最後給修復動作。",
            f"【{role_name}】你抓得很準，剛剛回覆有重覆傾向。我切成反鬼打牆模式，針對「{focus}」改給新資訊與下一步，不再重述舊段落。",
            f"【{role_name}】我改用不同角度回答「{focus}」：先講結論、再講原因、最後講你現在可做的單一步驟。若你要我直接動手，回我「執行」。",
        ]
        selected = self._pick_variant(variants, str(message or ""))
        if similarity >= self.max_reply_similarity:
            selected += f"\n（已避開近似回覆，上一輪相似度 {similarity:.2f}）"
        return selected

    def _apply_reply_diversity(
        self, message: str, role: str, analysis: dict, reply: str, workflow_ran: bool
    ) -> str:
        role_name = role or "總管"
        candidate = str(reply or "").strip()
        if not candidate:
            return candidate
        if workflow_ran:
            self._remember_role_reply(role_name, candidate)
            return candidate

        repetitive, similarity = self._is_reply_repetitive(role_name, candidate)
        if self.same_user_turn_count >= 2 or repetitive:
            candidate = self._build_loop_breaker_reply(
                message, role_name, analysis, similarity
            )
            self.last_diversified_reply = candidate
        self._remember_role_reply(role_name, candidate)
        return candidate

    def _message_has_execution_intent(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        action_tokens = (
            "執行", "修復", "修正", "解決", "優化", "debug", "偵測", "檢查",
            "安裝", "啟動", "重啟", "建立", "生成", "寫入", "更新", "測試",
            "run", "fix", "repair", "install", "start", "restart", "build", "test",
        )
        objective_tokens = (
            "git", "n8n", "docker", "cursor", "cmd", "api", "server", "伺服器", "workflow",
            "檔案", "文件", "md", "markdown", "repo", "branch", "commit", "push", "pull",
            "sqlite", "faiss", "資料庫", "記憶庫", "前端", "後端", "程式", "代碼", "code", "log",
        )
        direct_command_tokens = ("幫我", "請你", "請幫", "立刻", "馬上", "直接")
        has_action = any(token in text for token in action_tokens)
        has_objective = any(token in text for token in objective_tokens)
        if has_action and has_objective:
            return True
        if has_action and any(token in text for token in direct_command_tokens):
            return True
        hard_tokens = ("run", "debug", "git", "docker", "n8n", "workflow", "重啟服務", "啟動服務")
        return any(token in text for token in hard_tokens)

    def _is_dialog_quality_request(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        tokens = (
            "鬼打牆", "重複", "單一", "回覆化", "同內容", "同樣內容", "罐頭", "模板",
            "回答方式", "語氣", "回應低下", "過度單一", "對談模式", "不要重覆",
        )
        return any(token in text for token in tokens)

    def _is_langgraph_status_query(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        if "langgraph" not in text:
            return False
        status_tokens = ("可用", "不可用", "尚未可用", "是不是", "是否", "狀態", "available")
        return any(token in text for token in status_tokens)

    def _build_langgraph_status_guard_reply(self, role: str) -> str:
        role_name = str(role or "總管")
        available = self._langgraph_available_now(ttl_sec=5.0)
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if available:
            return (
                f"【{role_name}】本機即時檢查結果：LangGraph 目前可用。"
                f"\n- 檢查時間：{now_text}"
                "\n- 說明：你看到的「尚未可用」多半是舊記憶紀錄，不是現在狀態。"
            )
        return (
            f"【{role_name}】本機即時檢查結果：LangGraph 目前不可用。"
            f"\n- 檢查時間：{now_text}"
            "\n- 建議：先檢查 `langgraph` 套件與啟動環境，再重試 workflow。"
        )

    def _has_system_objective_request(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        tokens = (
            "git", "n8n", "docker", "cursor", "cmd", "api", "server", "伺服器", "workflow",
            "檔案", "文件", "md", "markdown", "repo", "branch", "commit", "push", "pull",
            "sqlite", "faiss", "資料庫", "記憶庫", "前端", "後端", "程式", "代碼", "code", "log",
        )
        return any(token in text for token in tokens)

    def _is_light_dialog_turn(self, message: str, purpose: str, interaction_mode: str) -> bool:
        text = str(message or "").strip()
        compact = re.sub(r"\s+", "", text.lower())
        if not compact:
            return True
        if interaction_mode in {"discussion", "qa", "creative"} and not self._message_has_execution_intent(text):
            return True
        if interaction_mode in {"coding", "workflow", "execution"}:
            return False
        greetings = {"你好", "嗨", "hi", "hello", "早安", "晚安", "在嗎", "回答我", "測試"}
        if compact in greetings:
            return True
        if len(compact) <= 28 and not self._message_has_execution_intent(text):
            return True
        return (purpose or "discussion") == "discussion" and not self._message_has_execution_intent(text)

    def _should_run_workflow(self, message: str, role: str, purpose: str, interaction_mode: str) -> bool:
        mode = self._normalize_interaction_mode(interaction_mode)
        if self._is_dialog_quality_request(message) and not self._has_system_objective_request(message):
            return False
        if mode in {"discussion", "qa", "creative"} and not self._message_has_execution_intent(message):
            return False
        if self._is_light_dialog_turn(message, purpose, mode):
            return False
        if mode in {"coding", "workflow", "execution"}:
            return True
        if (purpose or "").strip().lower() in {"execution", "workflow", "engineering", "security"}:
            return self._message_has_execution_intent(message)
        return self._message_has_execution_intent(message)

    def _build_conversational_reply(
        self,
        message: str,
        role: str,
        purpose: str,
        requested_backend: str,
        interaction_mode: str,
        analysis: dict,
        retrieval_brief: str = "",
    ) -> str:
        text = str(message or "").strip()
        compact = re.sub(r"\s+", "", text.lower())
        role_name = role or "總管"

        if compact in {"你好", "嗨", "hi", "hello", "在嗎"}:
            if role_name == "總管":
                return self._pick_variant(
                    [
                        "【總管】我在。現在用輕量對談模式：一般聊天不跑巡檢；你要我檢查或修復時，我再啟動工作流。",
                        "【總管】在線。先維持對談模式，避免工具清單洗版；你一句「執行」我就切工作流。",
                        "【總管】收到，這輪先不跑重型巡檢。你要我動手時，直接說「檢查」或「修復」。",
                    ],
                    text,
                )
            return self._pick_variant(
                [
                    f"【{role_name}】我在，先用輕量對談回覆。你可直接說要討論、整理、修復或查原因。",
                    f"【{role_name}】收到，先不啟動工具流。你若要我執行，補一句「執行」即可。",
                ],
                text,
            )

        cause_tokens = ("為什麼", "原因", "怎麼會", "以前不會", "變慢", "低下", "卡", "反應")
        if any(token in text for token in cause_tokens):
            return self._pick_variant(
                [
                    (
                        f"【{role_name}】核心原因是：先前路由把一般對談也送進工具工作流，"
                        "所以回覆變慢又偏報表。現在已改成雙軌：聊天走輕量、明確任務才跑工具。"
                    ),
                    (
                        f"【{role_name}】你看到的鬼打牆，主因是固定模板回覆比例太高。"
                        "我會保留任務模式，但把對談改成多變體並加上重複檢測。"
                    ),
                ],
                text,
            )

        if (
            not self._has_system_objective_request(text)
            and not self._message_has_execution_intent(text)
        ):
            return self._build_general_non_system_reply(
                message=text,
                role=role_name,
                analysis=analysis,
                loop_breaking=False,
                retrieval_brief=retrieval_brief,
            )

        topic = analysis.get("primary_topic") if isinstance(analysis, dict) else ""
        if role_name == "總管":
            return self._pick_variant(
                [
                    (
                        "【總管】我先用對談模式接住，不啟動工具巡檢。"
                        f"我抓到重點是「{topic or text[:24] or '目前對話'}」。"
                        "你要我動手時，直接加「執行 / 修復 / 檢查 / debug」。"
                    ),
                    (
                        f"【總管】先不進工具流，避免洗版。這句的焦點我判定為「{topic or text[:24] or '目前對話'}」。"
                        "若你要落地處理，我下一則就切工作流執行。"
                    ),
                ],
                text,
            )
        if role_name == "工程師":
            return self._pick_variant(
                [
                    "【工程師】先不跑重型流程。我先定位，再決定要不要改檔；你回「修復」或「執行測試」我就進工程工作流。",
                    "【工程師】我先給定位方向，不先啟動全套工具。需要我直接改碼時，回我「修復」。",
                ],
                text,
            )
        if role_name == "研究員":
            return self._pick_variant(
                [
                    "【研究員】先用討論模式整理脈絡；若要正式蒐集資料或產報告，再切研究任務。",
                    "【研究員】我先快速框問題，再看你要不要進入完整研究流程。",
                ],
                text,
            )
        if role_name == "小編":
            return self._pick_variant(
                [
                    "【小編】先用生活化方式回覆；若要輸出正式文案或腳本，再切製作流程。",
                    "【小編】我先做可讀版說明，等你確認後再產出可發布版本。",
                ],
                text,
            )
        if role_name == "帽子":
            return self._pick_variant(
                [
                    "【帽子】先做低干擾安全提醒；你要求掃描或權限檢查時，我再啟動工具鏈。",
                    "【帽子】這輪先不掃描，只給風險方向；你回「檢查」我就進安全流程。",
                ],
                text,
            )
        if role_name == "申言者":
            return self._pick_variant(
                [
                    "【申言者】先記錄規則與評分口徑；若要正式審核，我會列出扣分、加分與補救項。",
                    "【申言者】我先給評分框架，等你下令後再進正式審核。",
                ],
                text,
            )
        return self._pick_variant(
            [
                f"【{role_name}】我先用輕量對談模式回覆，不啟動工具巡檢。",
                f"【{role_name}】這輪先維持對談模式，避免重型流程打斷節奏。",
            ],
                text,
            )

    def _focus_topic(self, message: str, analysis: dict | None) -> str:
        text = str(message or "").strip()
        topic = ""
        if isinstance(analysis, dict):
            topic = str(analysis.get("primary_topic", "")).strip()
        weak_topic = (
            (not topic)
            or len(topic) < 4
            or ("給我" in topic)
            or ("並給" in topic)
            or bool(re.search(r"(請用|方式|步驟)$", topic))
        )
        if weak_topic:
            candidates = self._derive_turn_keywords(text, analysis or {}, limit=3)
            topic = candidates[0] if candidates else ""
        if not topic:
            cleaned = re.sub(r"[。！？!?，,；;：:\s]+", "", text)
            topic = cleaned[:22]
        return topic or "目前這題"

    def _extract_requested_count(self, text: str, default: int = 3, max_count: int = 5) -> int:
        raw = str(text or "")
        m = re.search(r"([1-9])\s*(個|點|條|步|件|招|方法|建議)", raw)
        if m:
            return min(max(1, int(m.group(1))), max_count)
        zh_map = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5}
        m2 = re.search(r"(一|二|兩|三|四|五)\s*(個|點|條|步|件|招|方法|建議)", raw)
        if m2:
            return min(max(1, zh_map.get(m2.group(1), default)), max_count)
        return min(max(1, int(default)), max_count)

    def _build_general_non_system_reply(
        self,
        message: str,
        role: str,
        analysis: dict | None,
        loop_breaking: bool = False,
        retrieval_brief: str = "",
    ) -> str:
        role_name = role or "總管"
        text = str(message or "").strip()
        focus = self._focus_topic(text, analysis or {})
        count = self._extract_requested_count(text, default=3, max_count=5)

        wellness_tokens = (
            "放鬆", "壓力", "焦慮", "心情", "緊張", "失眠", "過敏", "疲倦", "喘不過氣"
        )
        if any(token in text for token in wellness_tokens):
            steps = [
                "先降載 2 分鐘：離開螢幕，慢吸慢吐 10 次，讓身體先降速。",
                "做一個最小動作：喝水、洗臉或走 50 步，只選一件馬上做。",
                "把困擾寫成 1 句，接著只安排下一個 10 分鐘可完成的小任務。",
                "把刺激源先關一輪：通知靜音 20 分鐘，避免腦袋繼續過熱。",
                "若身體症狀持續（胸悶、心悸、失眠），今天先優先休息與就醫評估。",
            ]
            selected_steps = steps[:count]
            if loop_breaking:
                rotated = steps[1:] + steps[:1]
                selected_steps = rotated[:count]
            body = "\n".join(
                f"{idx}. {item}" for idx, item in enumerate(selected_steps, start=1)
            )
            prefix = "我換一組不重複版本，直接給你可做的步驟：" if loop_breaking else "先給你可立刻做的做法："
            if retrieval_brief:
                return f"【{role_name}】{prefix}\n{body}\n[關聯記憶] {retrieval_brief}"
            return f"【{role_name}】{prefix}\n{body}"

        explain_tokens = ("是什麼", "為什麼", "如何", "怎麼", "差異", "比較")
        if any(token in text for token in explain_tokens):
            base = (
                f"【{role_name}】我用白話整理「{focus}」：\n"
                "1. 先看結論：先抓重點，再處理細節，效率最高。\n"
                "2. 常見卡點：一次想解太多，反而每一步都卡住。\n"
                "3. 你現在可做：先做一個 10 分鐘可完成的最小步驟。"
            )
            if retrieval_brief:
                return base + f"\n[關聯記憶] {retrieval_brief}"
            return base

        generic = self._pick_variant(
            [
                (
                    f"【{role_name}】我直接回你這題，不走工程模板。\n"
                    f"1. 先把「{focus}」拆成目標與限制。\n"
                    "2. 先做一個最小可執行步驟（10 分鐘內）。\n"
                    "3. 把結果丟回來，我幫你做第二輪微調。"
                ),
                (
                    f"【{role_name}】我先給你實用版，不重述空話。\n"
                    f"1. 這題先定義成一句話：{focus}。\n"
                    "2. 先完成最小動作，再決定是否加碼。\n"
                    "3. 若你要，我下一則可改成清單/表格版。"
                ),
            ],
            text,
        )
        if retrieval_brief:
            return generic + f"\n[關聯記憶] {retrieval_brief}"
        return generic

    def _load_merged_env_data(self) -> dict:
        if cns_load_combined_env is not None:
            data, _ = cns_load_combined_env(self.workspace)
            return data
        return {}

    def _is_placeholder_token(self, value: str) -> bool:
        raw = str(value or "").strip()
        if not raw:
            return True
        if cns_is_placeholder_value is not None:
            try:
                return bool(cns_is_placeholder_value(raw))
            except Exception:
                pass
        lowered = raw.lower()
        return (
            "placeholder" in lowered
            or "example" in lowered
            or lowered.startswith("your_")
            or lowered.endswith("_here")
        )

    def _provider_runtime_config(self, backend: str) -> dict[str, Any]:
        provider = str(backend or "nvidia").strip().lower()
        if provider not in {"nvidia", "openai", "groq", "gemini"}:
            provider = "nvidia"

        env = self._load_merged_env_data()
        cfg: dict[str, Any] = {}
        if cns_resolve_provider_config is not None:
            try:
                cfg = cns_resolve_provider_config(self.workspace, provider) or {}
            except Exception:
                cfg = {}

        key_names = {
            "nvidia": ("NVAPI_API_KEY", "OPENAI_API_KEY"),
            "openai": ("OPENAI_API_KEY",),
            "groq": ("GROQ_API_KEY",),
            "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        }
        base_names = {
            "nvidia": ("NVIDIA_BASE_URL", "OPENAI_BASE_URL"),
            "openai": ("OPENAI_PROVIDER_BASE_URL", "OPENAI_BASE_URL"),
            "groq": ("GROQ_BASE_URL", "OPENAI_BASE_URL"),
            "gemini": ("GEMINI_BASE_URL", "OPENAI_BASE_URL"),
        }
        model_names = {
            "nvidia": ("NVIDIA_MODEL", "OPENAI_MODEL"),
            "openai": ("OPENAI_PROVIDER_MODEL", "OPENAI_MODEL"),
            "groq": ("GROQ_MODEL", "OPENAI_MODEL"),
            "gemini": ("GEMINI_MODEL", "OPENAI_MODEL"),
        }
        default_base = {
            "nvidia": "https://integrate.api.nvidia.com/v1",
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
        }

        key = str(cfg.get("key", "") or "").strip()
        key_name = str(cfg.get("key_name", "") or "").strip()
        if self._is_placeholder_token(key):
            key = ""
        if not key:
            for name in key_names[provider]:
                candidate = str(env.get(name, "") or "").strip()
                if candidate and not self._is_placeholder_token(candidate):
                    key = candidate
                    key_name = name
                    break

        base_url = str(cfg.get("base_url", "") or "").strip()
        if self._is_placeholder_token(base_url):
            base_url = ""
        if not base_url:
            for name in base_names[provider]:
                candidate = str(env.get(name, "") or "").strip()
                if candidate and not self._is_placeholder_token(candidate):
                    base_url = candidate
                    break
        if not base_url:
            base_url = default_base[provider]

        model = str(cfg.get("model", "") or "").strip()
        if self._is_placeholder_token(model):
            model = ""
        if not model:
            for name in model_names[provider]:
                candidate = str(env.get(name, "") or "").strip()
                if candidate and not self._is_placeholder_token(candidate):
                    model = candidate
                    break
        if not model:
            model = DEFAULT_CHAT_MODEL_BY_PROVIDER.get(provider, "")

        return {
            "provider": provider,
            "key": key,
            "key_name": key_name or key_names[provider][0],
            "base_url": str(base_url).rstrip("/"),
            "model": model,
        }

    def _extract_openai_message_text(self, payload: dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message", {}) if isinstance(first, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            pieces: list[str] = []
            for item in content:
                if isinstance(item, str):
                    pieces.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "") or item.get("content", "") or "").strip()
                if text:
                    pieces.append(text)
            return "\n".join(piece for piece in pieces if piece).strip()
        return ""

    def _call_openai_compatible_chat(
        self, backend: str, messages: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any]]:
        runtime = self._provider_runtime_config(backend)
        key = str(runtime.get("key", "") or "").strip()
        base_url = str(runtime.get("base_url", "") or "").strip().rstrip("/")
        model = str(runtime.get("model", "") or "").strip()
        provider = str(runtime.get("provider", backend) or backend).strip().lower()
        if not key:
            raise RuntimeError(f"{provider}: API key missing")
        if not base_url:
            raise RuntimeError(f"{provider}: base_url missing")
        if not model:
            raise RuntimeError(f"{provider}: model missing")

        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        req_payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.live_llm_temperature,
            "max_tokens": self.live_llm_max_tokens,
            "stream": False,
        }
        data = json.dumps(req_payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.live_llm_timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:260]
            raise RuntimeError(f"{provider}: http {exc.code} {detail}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"{provider}: network {exc.reason}") from exc

        payload = json.loads(body or "{}")
        text = self._extract_openai_message_text(payload)
        if not text:
            raise RuntimeError(f"{provider}: empty_response")
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        meta = {
            "ok": True,
            "transport": "openai_compatible",
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "usage": usage if isinstance(usage, dict) else {},
        }
        return text.strip(), meta

    def _call_ollama_chat(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any]]:
        env = self._load_merged_env_data()
        endpoint = str(env.get("OLLAMA_CHAT_URL", "http://127.0.0.1:11434/api/chat") or "").strip()
        model = str(
            env.get("OPEN_SOURCE_CHAT_MODEL", "")
            or env.get("OLLAMA_MODEL", "")
            or DEFAULT_CHAT_MODEL_BY_PROVIDER.get("open_source", "qwen2.5:7b")
        ).strip()
        req_payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.live_llm_temperature},
        }
        data = json.dumps(req_payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.live_llm_timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:260]
            raise RuntimeError(f"open_source: http {exc.code} {detail}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"open_source: network {exc.reason}") from exc

        payload = json.loads(body or "{}")
        message_obj = payload.get("message", {}) if isinstance(payload, dict) else {}
        content = str(message_obj.get("content", "") or "").strip() if isinstance(message_obj, dict) else ""
        if not content:
            raise RuntimeError("open_source: empty_response")
        meta = {
            "ok": True,
            "transport": "ollama",
            "provider": "open_source",
            "model": model,
            "endpoint": endpoint,
        }
        return content, meta

    def _build_live_llm_messages(
        self,
        role: str,
        user_message: str,
        retrieval_brief: str = "",
    ) -> list[dict[str, str]]:
        role_name = str(role or "總管").strip() or "總管"
        system_prompt = self._get_dynamic_system_prompt(role_name)
        behavior_guard = (
            "請使用繁體中文，優先直接回答問題本身，不要只回模板話術。"
            "若有不確定處要誠實說明，並給最小可執行下一步。"
        )
        memory_hint = ""
        if retrieval_brief:
            memory_hint = f"[關聯記憶摘要]\n{retrieval_brief}"
        composed_user = self._compose_model_message(
            agent_name=role_name,
            user_message=user_message,
            plan="",
            workflow_memory_context=memory_hint,
        )
        return [
            {"role": "system", "content": f"{system_prompt}\n\n{behavior_guard}".strip()},
            {"role": "user", "content": composed_user.strip()},
        ]

    def _generate_live_llm_reply(
        self,
        message: str,
        role: str,
        requested_backend: str,
        retrieval_brief: str = "",
    ) -> tuple[str, dict[str, Any]]:
        if not self.enable_live_llm_default:
            return "", {
                "ok": False,
                "attempted": False,
                "fallback_reason": "CHAT_LIVE_LLM_DEFAULT=off",
            }

        backend = str(requested_backend or "nvidia").strip().lower()
        messages = self._build_live_llm_messages(
            role=role,
            user_message=message,
            retrieval_brief=retrieval_brief,
        )
        try:
            if backend == "open_source":
                reply, meta = self._call_ollama_chat(messages)
            else:
                reply, meta = self._call_openai_compatible_chat(backend, messages)
            result = dict(meta or {})
            result["attempted"] = True
            result["fallback_used"] = False
            return reply, result
        except Exception as exc:
            return "", {
                "ok": False,
                "attempted": True,
                "fallback_used": True,
                "provider": backend,
                "fallback_reason": str(exc),
            }

    def _get_dynamic_system_prompt(self, agent_name: str) -> str:
        return get_agent_system_prompt(agent_name, self.workspace)

    def _requested_backend_for_purpose(self, purpose: str) -> str:
        env = self._load_merged_env_data()
        if purpose == "execution":
            return "nvidia"
        pref = str(env.get("CHAT_PREFERRED_PROVIDER", "")).strip().lower()
        if pref in {"nvidia", "openai", "groq", "gemini"}:
            return pref
        return "open_source"

    def _is_cloud_available(self, backend: str) -> bool:
        env = self._load_merged_env_data()
        key_map = {
            "nvidia": "NVAPI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        key_name = key_map.get(backend)
        if not key_name: return False
        val = str(env.get(key_name, "")).strip()
        if not val or "placeholder" in val.lower() or len(val) < 12:
            return False
        return True

    def _build_react_loop(
        self,
        message: str,
        purpose: str,
        interaction_mode: str,
        should_run_workflow: bool,
        analysis: dict,
    ) -> dict:
        topic = ""
        if isinstance(analysis, dict):
            topic = str(analysis.get("primary_topic", "")).strip()
        thought = (
            f"User intent={purpose or 'discussion'}; mode={interaction_mode}; "
            f"topic={topic or 'general'}; workflow={bool(should_run_workflow)}"
        )
        action = "run_workflow" if should_run_workflow else "conversation_reply"
        completion = (
            "Provide executable result with verification notes."
            if should_run_workflow
            else "Provide non-repetitive, context-aware reply."
        )
        return {
            "thought": thought,
            "action": action,
            "completion_criteria": completion,
            "observation": "",
            "refinement": "",
        }

    def _summarize_workflow_observation(
        self, workflow_payload: dict, workflow_ran: bool, reply: str
    ) -> str:
        if workflow_ran and isinstance(workflow_payload, dict):
            task = workflow_payload.get("task_state", {}) or {}
            return (
                f"workflow_status={task.get('overall_status', 'unknown')}; "
                f"completed={task.get('completed_steps', 0)}; "
                f"failed={task.get('failed_steps', 0)}"
            )
        return f"conversation_reply_len={len(str(reply or '').strip())}"

    def _evaluate_completion(
        self, should_run_workflow: bool, workflow_payload: dict, workflow_ran: bool, reply: str
    ) -> dict:
        reply_text = str(reply or "").strip()
        if not should_run_workflow:
            return {
                "done": bool(reply_text),
                "state": "completed" if bool(reply_text) else "incomplete",
                "reason": "conversation_mode",
            }
        if not workflow_ran:
            return {"done": False, "state": "incomplete", "reason": "workflow_not_executed"}
        task = workflow_payload.get("task_state", {}) if isinstance(workflow_payload, dict) else {}
        status = str(task.get("overall_status", "")).strip().lower()
        completed_steps = int(task.get("completed_steps", 0) or 0)
        failed_steps = int(task.get("failed_steps", 0) or 0)
        done = status in {"success", "partial"} and completed_steps > 0 and bool(reply_text)
        return {
            "done": done,
            "state": "completed" if done else "incomplete",
            "reason": status or "unknown",
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
        }

    def _detect_high_risk_action(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        return any(token in text for token in self.high_risk_action_tokens)

    def _should_escalate_to_human(
        self, message: str, completion: dict, should_run_workflow: bool
    ) -> tuple[bool, str]:
        if not should_run_workflow:
            return False, ""
        if completion.get("done"):
            self.workflow_fail_streak = 0
            return False, ""
        self.workflow_fail_streak += 1
        if self.workflow_fail_streak >= self.auto_escalate_fail_streak:
            return True, "workflow_failed_repeatedly"
        if self._detect_high_risk_action(message):
            return True, "high_risk_action_requires_review"
        return False, ""

    def _build_human_escalation_reply(self, reason: str) -> str:
        if reason == "high_risk_action_requires_review":
            return (
                "這個請求涉及高風險操作，我已暫停自動執行，請由人類工程師/小編覆核後再繼續。"
            )
        return (
            f"我已連續 {self.workflow_fail_streak} 次未達成完成條件，已觸發人工覆核。"
            "請確認目標與限制後，我再繼續執行。"
        )

    def send_message(self, message: str, role: str = "總管", session_id: str = "", model_key: str = "auto", interaction_mode: str = "auto") -> dict:
        start_ts = time.time()
        self.last_message = message
        self.last_message_ts = start_ts
        self.reply_counter += 1
        self._update_user_repeat_tracking(message)
        
        # 語義分析
        analysis = {}
        if analyze_message:
            try:
                analysis = analyze_message(message)
            except Exception:
                analysis = self._fallback_message_analysis(message)
        else:
            analysis = self._fallback_message_analysis(message)
        self.last_message_analysis = analysis
        turn_keywords = self._derive_turn_keywords(message, analysis)
        retrieval_payload = self._run_keyword_retrieval(turn_keywords, per_keyword=2)
        retrieval_brief = self._build_retrieval_brief(retrieval_payload)
        
        # 決定後端
        interaction_mode = self._normalize_interaction_mode(interaction_mode)
        purpose = infer_backend_purpose(message) if infer_backend_purpose else "discussion"
        requested_backend = model_key if model_key != "auto" else self._requested_backend_for_purpose(purpose)
        
        # 雲端優先邏輯
        if requested_backend == "open_source" and not self.oss_is_healthy:
            if self._is_cloud_available("nvidia"): requested_backend = "nvidia"
            elif self._is_cloud_available("groq"): requested_backend = "groq"
        
        self._requested_backend = requested_backend
        
        reply = ""
        workflow_payload: dict = {}
        workflow_ran = False
        live_llm_meta: dict[str, Any] = {
            "ok": False,
            "attempted": False,
            "fallback_used": False,
            "provider": requested_backend,
        }
        workflow_payload["retrieval"] = retrieval_payload
        workflow_payload["keywords"] = turn_keywords
        if retrieval_brief:
            workflow_payload["retrieval_brief"] = retrieval_brief
        should_run_workflow = self._should_run_workflow(message, role, purpose, interaction_mode)
        react_loop = self._build_react_loop(
            message=message,
            purpose=purpose,
            interaction_mode=interaction_mode,
            should_run_workflow=should_run_workflow,
            analysis=analysis,
        )
        workflow_payload["react"] = dict(react_loop)

        if (not should_run_workflow) and self._is_langgraph_status_query(message):
            reply = self._build_langgraph_status_guard_reply(role)
            live_llm_meta = {
                "ok": False,
                "attempted": False,
                "fallback_used": True,
                "provider": requested_backend,
                "fallback_reason": "langgraph_status_guard",
            }
            workflow_payload["llm_live"] = dict(live_llm_meta)

        # 明確任務才啟動 LangGraph；一般總管聊天保持輕量對談。
        if should_run_workflow and not reply.strip():
            try:
                from core.langgraph_workflow import run_workflow
                wf_result = run_workflow(message, workspace=str(self.workspace))
                self.last_workflow_state = wf_result
                if isinstance(wf_result, dict):
                    workflow_payload.update(wf_result)
                else:
                    workflow_payload["raw"] = wf_result
                workflow_ran = True
                route = workflow_payload.get("route", role)
                result = str(workflow_payload.get("result", "")).strip()
                verification = str(workflow_payload.get("verification_notes", "")).strip()
                risk_level = str(workflow_payload.get("risk_level", "L0")).strip()
                precheck = str(workflow_payload.get("precheck_owner", "無")).strip()
                if result:
                    reply = f"【{route}】\n{result}"
                    if verification:
                        reply += f"\n\n[驗證]\n{verification}"
                    if precheck != "無":
                        reply += f"\n[風險分級] {risk_level}（前置：{precheck}）"
            except Exception as e:
                reply = f"【{role}】工作流執行失敗：{e}"
            live_llm_meta = {
                "ok": False,
                "attempted": False,
                "fallback_used": True,
                "provider": requested_backend,
                "fallback_reason": "workflow_mode",
            }
            workflow_payload["llm_live"] = dict(live_llm_meta)
        elif (not should_run_workflow) and (not reply.strip()):
            live_reply, live_llm_meta = self._generate_live_llm_reply(
                message=message,
                role=role,
                requested_backend=requested_backend,
                retrieval_brief=retrieval_brief,
            )
            if live_reply.strip():
                reply = live_reply.strip()
            workflow_payload["llm_live"] = dict(live_llm_meta)

        # 後備回覆：一般對談避免暴露巡檢細節；任務失敗才給簡短狀態。
        if not reply.strip():
            if not should_run_workflow:
                reply = self._build_conversational_reply(
                    message,
                    role,
                    purpose,
                    requested_backend,
                    interaction_mode,
                    analysis,
                    retrieval_brief,
                )
            else:
                reply = (
                    f"【{role}】我有收到任務，但工具流沒有產出可讀結果。"
                    f"\n- 問題摘要：{message[:60]}"
                    f"\n- 模式：{interaction_mode}"
                    f"\n- 後端：{requested_backend}"
                )
        if (
            not should_run_workflow
            and not live_llm_meta.get("attempted")
            and not live_llm_meta.get("fallback_reason")
        ):
            live_llm_meta = {
                "ok": False,
                "attempted": False,
                "fallback_used": True,
                "provider": requested_backend,
                "fallback_reason": "no_live_call",
            }
            workflow_payload["llm_live"] = dict(live_llm_meta)
        elif not should_run_workflow and not live_llm_meta.get("ok"):
            workflow_payload["llm_live"] = dict(live_llm_meta)
        self.last_live_llm_meta = dict(live_llm_meta)

        reply = self._apply_reply_diversity(
            message=message,
            role=role,
            analysis=analysis,
            reply=reply,
            workflow_ran=workflow_ran,
        )

        completion = self._evaluate_completion(
            should_run_workflow=should_run_workflow,
            workflow_payload=workflow_payload,
            workflow_ran=workflow_ran,
            reply=reply,
        )
        react_loop["observation"] = self._summarize_workflow_observation(
            workflow_payload=workflow_payload, workflow_ran=workflow_ran, reply=reply
        )
        react_loop["refinement"] = (
            "Escalate to human reviewer." if not completion.get("done") else "Proceed."
        )
        workflow_payload["react"] = dict(react_loop)

        escalation_required, escalation_reason = self._should_escalate_to_human(
            message=message,
            completion=completion,
            should_run_workflow=should_run_workflow,
        )
        escalation = {
            "required": bool(escalation_required),
            "reason": escalation_reason,
            "fail_streak": int(self.workflow_fail_streak),
        }
        if escalation_required:
            completion["state"] = "escalated"
            completion["done"] = False
            reply += "\n\n[人工覆核]\n" + self._build_human_escalation_reply(escalation_reason)

        self._remember_dialog_turn(
            user_message=message,
            assistant_message=reply,
            analysis=analysis,
            workflow_ran=workflow_ran,
        )
        self._record_turn_artifacts(
            session_id=session_id,
            role=role,
            user_message=message,
            assistant_message=reply,
            analysis=analysis,
            keywords=turn_keywords,
            retrieval=retrieval_payload,
            workflow_ran=workflow_ran,
            backend=requested_backend,
            purpose=purpose,
            interaction_mode=interaction_mode,
        )
        self._persist_training_overlay_sample(
            session_id=session_id,
            role=role,
            user_message=message,
            assistant_message=reply,
            analysis=analysis,
            keywords=turn_keywords,
            workflow_ran=workflow_ran,
            backend=requested_backend,
        )

        # 強制存入永久記憶 (Permanent Memory Save)
        if self.memory_manager:
            try:
                self.memory_manager.save_conversation(
                    agent_name=role,
                    user_message=message,
                    assistant_message=reply,
                    metadata={
                        "backend": requested_backend,
                        "workflow_ran": workflow_ran,
                        "mode": interaction_mode,
                        "purpose": purpose,
                        "completion_state": completion.get("state", ""),
                        "escalation_required": bool(escalation_required),
                        "react_action": react_loop.get("action", ""),
                        "keywords": turn_keywords[:8],
                        "retrieval_match_count": int(retrieval_payload.get("match_count", 0) or 0),
                    }
                )
            except Exception:
                pass

        duration = round(time.time() - start_ts, 3)
        self.last_reply = reply
        
        return {
            "ok": True,
            "reply": reply,
            "role": role,
            "agent": self._role_to_agent_key(role),
            "backend": requested_backend,
            "duration_s": duration,
            "response_time": duration,
            "analysis": analysis,
            "semantic_analysis": analysis,
            "keywords": turn_keywords,
            "retrieval": retrieval_payload,
            "workflow": workflow_payload,
            "workflow_ran": workflow_ran,
            "llm_live": live_llm_meta,
            "purpose": purpose,
            "interaction_mode": interaction_mode,
            "model": requested_backend,
            "completion": completion,
            "escalation": escalation,
            "react": react_loop,
        }

    def _system_profile(self) -> dict:
        if psutil:
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
            }
        return {"cpu_percent": 0, "memory_percent": 0}

    def _api_health(self) -> dict:
        if cns_llm_snapshot is not None:
            try:
                snapshot = cns_llm_snapshot(self.workspace) or {}
                return {
                    "key_source": str(snapshot.get("key_source", "NVAPI_API_KEY")),
                    "key_state": str(snapshot.get("key_state", "未知")),
                    "model_state": str(snapshot.get("model", "未設定")),
                    "open_source_model": str(snapshot.get("open_source_model", "未設定")),
                }
            except Exception:
                pass
        env = self._load_merged_env_data()
        nv_key = str(env.get("NVAPI_API_KEY", "") or "").strip()
        model = str(env.get("OPENAI_MODEL", "") or "").strip() or "未設定"
        return {
            "key_source": "NVAPI_API_KEY",
            "key_state": "已設定" if len(nv_key) > 20 else "未設定",
            "model_state": model,
            "open_source_model": str(
                env.get("OPEN_SOURCE_CHAT_MODEL", env.get("OLLAMA_MODEL", "未設定"))
            ),
        }

    def _git_status_filtered(self, short: bool = True) -> str:
        return "Git 功能受限 (Mock)"

    def _vscode_status(self) -> dict:
        return {"integration_state": "未偵測", "process_running": False}

    def get_status(self) -> dict:
        return {
            "reply_counter": self.reply_counter,
            "last_message_ts": self.last_message_ts,
            "system": self._system_profile()
        }

    def get_api_onboarding_info(self) -> dict:
        if cns_frontend_provider_status is not None:
            try:
                return {"providers": cns_frontend_provider_status(self.workspace)}
            except Exception:
                pass
        if cns_provider_matrix is not None:
            try:
                env = self._load_merged_env_data()
                rows = cns_provider_matrix(env)
                return {"providers": {"rows": rows}}
            except Exception:
                pass
        return {"providers": {}}

    def _get_available_models(self) -> list:
        return [{"name": "qwen2.5:7b", "size_gb": 4.7}]

    def open_external(self, url: str) -> bool:
        webbrowser.open(url)
        return True

    def rerun_workflow_step(self, task_id: str, tool_name: str, step_index: int) -> dict:
        return {"ok": False, "message": "此模式暫不支援重跑步驟"}

    def _load_offline_replies(self) -> dict:
        return {"總管": ["離線模式已就緒"]}

    def _init_quick_replies(self) -> list:
        return [{"id": "status", "text": "檢查系統狀態"}]

    def _broadcast_reminder_js(self, msg: str):
        print(f"📢 系統提醒: {msg}")

    def _check_and_send_reminder(self, now: float) -> str:
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="desktop", choices=["web", "desktop"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--energy-lite", action="store_true")
    parser.add_argument("--unified", action="store_true")
    args = parser.parse_args()

    bridge = DesktopBridge(energy_lite=args.energy_lite)

    if args.mode == "web":
        return run_web_server_mode(bridge, bridge.workspace, args.host, args.port, args.open_browser)
    
    # 桌面模式
    try:
        import webview
    except ImportError:
        print("❌ 找不到 pywebview，請執行 pip install pywebview")
        return 1
        
    bridge.window = webview.create_window(
        "智能體控制中心", 
        url=str(CHAT_SHELL_HTML),
        js_api=bridge,
        width=1200, height=800
    )
    webview.start(debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())


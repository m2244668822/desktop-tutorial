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
import json
import os
import re
import subprocess
import sys
import threading
import time
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
        self.max_context = 3
        self.max_context_summary_length = 200
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

        # 路徑跟隨 workspace（使用 centralized paths）
        self.env_file = self.paths.env_main
        self.env_candidates = self.paths.env_candidates
        self.catalog_json = self.paths.catalog_json
        self.relay_log = self.workspace / "logs" / "manager_relay_status.jsonl"
        
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
            "faiss_ready": bool(status.get("faiss_ready")),
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
        if len(text) > 80 or any(
            token in text.lower()
            for token in ["api", "langgraph", "架構", "模型", "記憶", "設定"]
        ):
            return 5
        return 3

    def _search_long_term_memory(self, query: str, top_k: int) -> list[dict]:
        if not self.long_term_memory_api or not query.strip():
            return []
        try:
            return self.long_term_memory_api.search_long_term_memory(query, top_k=top_k)
        except Exception:
            return []

    def _build_long_term_memory_block(
        self, query: str, top_k: int | None = None, max_chars: int = 700
    ) -> str:
        selected_k = top_k or self._long_term_memory_top_k(query)
        matches = self._search_long_term_memory(query, selected_k)
        if not matches:
            return ""

        lines = ["[長期記憶摘要]"]
        used_chars = len(lines[0])
        for idx, item in enumerate(matches[:selected_k], start=1):
            source = item.get("source", "unknown")
            timestamp = str(item.get("timestamp", "") or "未知時間")[:19]
            summary = " ".join(str(item.get("summary", "")).split())
            if not summary:
                continue
            entry = f"{idx}. 來源={source} | 時間={timestamp} | 摘要={summary[:160]}"
            if used_chars + len(entry) > max_chars:
                break
            lines.append(entry)
            used_chars += len(entry)
        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_recent_context_block(self) -> str:
        context_info = ""
        if self.conversation_context:
            context_info = "\n\n最近的對話上下文：\n" + "\n".join(
                [
                    f"{'👤' if ctx.get('role') == 'user' else '🤖'} {ctx.get('content', '')[:50]}"
                    for ctx in self.conversation_context[-3:]
                ]
            )
        if self.context_summary:
            context_info += f"\n[壓縮歷史] {self.context_summary[:100]}"
        context_info += f"\n[對話統計] 回覆 #{self.reply_counter}"
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
        recent_context = self._build_recent_context_block()
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

    def _load_merged_env_data(self) -> dict:
        if cns_load_combined_env is not None:
            data, _ = cns_load_combined_env(self.workspace)
            return data
        return {}

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

    def send_message(self, message: str, role: str = "總管", session_id: str = "", model_key: str = "auto") -> dict:
        start_ts = time.time()
        self.last_message = message
        self.last_message_ts = start_ts
        self.reply_counter += 1
        
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
        
        # 決定後端
        purpose = infer_backend_purpose(message) if infer_backend_purpose else "discussion"
        requested_backend = model_key if model_key != "auto" else self._requested_backend_for_purpose(purpose)
        
        # 雲端優先邏輯
        if requested_backend == "open_source" and not self.oss_is_healthy:
            if self._is_cloud_available("nvidia"): requested_backend = "nvidia"
            elif self._is_cloud_available("groq"): requested_backend = "groq"
        
        self._requested_backend = requested_backend
        
        reply = ""
        workflow_payload: dict = {}

        # 以 LangGraph 工作流為主線，避免模板化回覆
        if role == "總管" or purpose in {"execution", "workflow", "engineering", "security"}:
            try:
                from core.langgraph_workflow import run_workflow
                wf_result = run_workflow(message, workspace=str(self.workspace))
                self.last_workflow_state = wf_result
                workflow_payload = wf_result
                route = wf_result.get("route", role)
                result = str(wf_result.get("result", "")).strip()
                verification = str(wf_result.get("verification_notes", "")).strip()
                risk_level = str(wf_result.get("risk_level", "L0")).strip()
                precheck = str(wf_result.get("precheck_owner", "無")).strip()
                if result:
                    reply = f"【{route}】\n{result}"
                    if verification:
                        reply += f"\n\n[驗證]\n{verification}"
                    if precheck != "無":
                        reply += f"\n[風險分級] {risk_level}（前置：{precheck}）"
            except Exception as e:
                reply = f"【{role}】工作流執行失敗：{e}"

        # 後備回覆：若工作流未產出內容，至少避免重複模板語
        if not reply.strip():
            role_prompt = self._get_dynamic_system_prompt(role)
            short_prompt = " ".join(role_prompt.split())[:160]
            reply = (
                f"【{role}】我已接手此任務，將依據目前分流規則處理。"
                f"\n- 問題摘要：{message[:60]}"
                f"\n- 使用後端：{requested_backend}"
                f"\n- 角色策略：{short_prompt}"
            )

        duration = round(time.time() - start_ts, 3)
        self.last_reply = reply
        
        return {
            "ok": True,
            "reply": reply,
            "role": role,
            "backend": requested_backend,
            "duration_s": duration,
            "analysis": analysis,
            "workflow": workflow_payload,
        }

    def _system_profile(self) -> dict:
        if psutil:
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
            }
        return {"cpu_percent": 0, "memory_percent": 0}

    def _api_health(self) -> dict:
        env = self._load_merged_env_data()
        nv_key = env.get("NVAPI_API_KEY", "")
        return {
            "key_source": "NVAPI_API_KEY",
            "key_state": "已設定" if len(nv_key) > 20 else "未設定",
            "model_state": "qwen2.5:7b" if self.oss_is_healthy else "雲端模式"
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
        return {"providers": PROVIDER_PROFILES} if 'PROVIDER_PROFILES' in globals() else {"providers": []}

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

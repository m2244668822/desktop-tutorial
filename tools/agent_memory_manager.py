#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體統一記憶管理系統 (Agent Unified Memory Manager)

功能：
1. 智能體記憶持久化 - 所有智能體的狀態、偏好、學習成果持久化儲存
2. 對話上下文保存 - 完整對話歷史持久化，包括用戶/助手訊息對
3. IDE上下文保存 - VSCode 狀態、工作區資訊、打開的檔案等

使用方式：
from agent_memory_manager import AgentMemoryManager
memory_manager = AgentMemoryManager()

# 保存智能體記憶
memory_manager.save_agent_memory("總管", {"last_task": "...", "learned_preferences": {...}})

# 保存對話
memory_manager.save_conversation("總管", "用戶訊息", "助手回覆")

# 保存IDE上下文
memory_manager.save_ide_context({"workspace": "...", "open_files": [...], "vscode_status": {...}})
"""

import json
import os
import sys
import time as time_module
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import hashlib


def _configure_utf8_stdio() -> None:
    """Keep Windows terminals from crashing on UTF-8 status text."""
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_configure_utf8_stdio()


def _resolve_data_root(base_dir: Path) -> Path:
    primary = base_dir / "data"
    fallback = base_dir / "data_hdd_storage"
    if primary.is_dir():
        return primary
    if fallback.is_dir():
        return fallback
    if primary.exists() and not primary.is_dir():
        return fallback
    return primary


class AgentMemoryManager:
    """智能體統一記憶管理系統"""

    def __init__(
        self, base_dir: str = None, auto_save: bool = True
    ):
        """
        初始化智能體記憶管理系統

        Args:
            base_dir: 基礎目錄
            auto_save: 是否自動保存（定時自動保存）
        """
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]
        self.auto_save = auto_save
        self._lock = threading.Lock()

        # 記憶存儲路徑
        data_root = _resolve_data_root(self.base_dir)
        self.memory_dir = data_root / "agent_memories"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 各類記憶文件
        self.agent_memory_file = self.memory_dir / "agent_memories.json"
        self.conversation_file = self.memory_dir / "conversations.json"
        self.ide_context_file = self.memory_dir / "ide_context.json"
        self.session_file = self.memory_dir / "sessions.json"

        # 內存緩存
        self._agent_memories = {}
        self._conversations = {}
        self._ide_context = {}
        self._sessions = {}

        # 最後保存時間
        self._last_save_time = datetime.now()
        self._save_interval = timedelta(seconds=30)  # 自動保存間隔

        # 保存失敗追蹤與重試機制
        self._save_failures = 0
        self._max_save_failures = 3
        self._last_save_error = None
        self._save_retry_pending = False
        self._backup_dir = self.memory_dir / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # 初始化
        self._load_all()
        self._auto_recover_conversations()

        # 啟動定時保存線程
        if self.auto_save:
            self._start_auto_save()

        print(f"✅ 智能體統一記憶管理系統已初始化")
        print(f"   記憶目錄: {self.memory_dir}")
        print(f"   自動保存: {'啟用' if self.auto_save else '停用'}")

    def _auto_recover_conversations(self):
        """若主 conversations 過少，自動從可用備份來源補回（不覆蓋現有）。"""
        try:
            current_count = len(self._conversations) if isinstance(self._conversations, dict) else 0
            if current_count >= 20:
                return

            merged = dict(self._conversations or {})
            recovered = 0

            # 來源 1: HDD 鏡像（同格式）
            hdd_conv = self.base_dir / "data_hdd_storage" / "agent_memories" / "conversations.json"
            if hdd_conv.exists():
                try:
                    data = json.loads(hdd_conv.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        for cid, payload in data.items():
                            if cid not in merged and isinstance(payload, dict):
                                merged[cid] = payload
                                recovered += 1
                except Exception:
                    pass

            # 來源 2: 舊 GPT conversations list（prompt/response）轉為通用 thread
            legacy_conv = self.base_dir / "500" / "llama32-chat" / "data" / "conversations.json"
            if legacy_conv.exists():
                try:
                    rows = json.loads(legacy_conv.read_text(encoding="utf-8"))
                    if isinstance(rows, list):
                        for idx, row in enumerate(rows):
                            if not isinstance(row, dict):
                                continue
                            prompt = str(row.get("prompt", "")).strip()
                            response = str(row.get("response", "")).strip()
                            if not prompt and not response:
                                continue
                            ts = str(row.get("timestamp", ""))
                            conv_id = f"legacy-{idx:06d}"
                            if conv_id in merged:
                                continue
                            merged[conv_id] = {
                                "agent_name": "通用",
                                "created_at": ts,
                                "last_message_at": ts,
                                "messages": [
                                    {
                                        "timestamp": ts,
                                        "user": prompt,
                                        "assistant": response,
                                        "metadata": {
                                            "source": "legacy_llama32_chat",
                                            "model": row.get("model", ""),
                                            "status": row.get("status", ""),
                                        },
                                    }
                                ],
                            }
                            recovered += 1
                except Exception:
                    pass

            if recovered > 0:
                self._conversations = merged
                self._save_conversations()
                print(f"   ♻️ 已自動恢復對話記錄: +{recovered}（總計 {len(self._conversations)}）")
        except Exception as e:
            print(f"   ⚠️ 自動恢復對話記錄失敗: {e}")

    def _load_all(self):
        """加載所有記憶數據"""
        self._load_agent_memories()
        self._load_conversations()
        self._load_ide_context()
        self._load_sessions()

    def _load_agent_memories(self):
        """加載智能體記憶"""
        if self.agent_memory_file.exists():
            try:
                with open(self.agent_memory_file, "r", encoding="utf-8") as f:
                    self._agent_memories = json.load(f)
                print(f"   📦 已加載 {len(self._agent_memories)} 個智能體記憶")
            except Exception as e:
                print(f"   ⚠️ 加載智能體記憶失敗: {e}")
                self._agent_memories = {}

    def _load_conversations(self):
        """加載對話歷史"""
        if self.conversation_file.exists():
            try:
                with open(self.conversation_file, "r", encoding="utf-8") as f:
                    self._conversations = json.load(f)
                total_messages = sum(
                    len(conv.get("messages", []))
                    for conv in self._conversations.values()
                )
                print(
                    f"   💬 已加載 {len(self._conversations)} 個對話記錄 ({total_messages} 條訊息)"
                )
            except Exception as e:
                print(f"   ⚠️ 加載對話歷史失敗: {e}")
                self._conversations = {}

    def _load_ide_context(self):
        """加載IDE上下文"""
        if self.ide_context_file.exists():
            try:
                with open(self.ide_context_file, "r", encoding="utf-8") as f:
                    self._ide_context = json.load(f)
                print(f"   🖥️ 已加載IDE上下文")
            except Exception as e:
                print(f"   ⚠️ 加載IDE上下文失敗: {e}")
                self._ide_context = {}

    def _load_sessions(self):
        """加載會話記錄"""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    self._sessions = json.load(f)
                print(f"   📋 已加載 {len(self._sessions)} 個會話記錄")
            except Exception as e:
                print(f"   ⚠️ 加載會話記錄失敗: {e}")
                self._sessions = {}

    def _start_auto_save(self):
        """啟動定時自動保存"""

        def auto_save_loop():
            while self.auto_save:
                try:
                    time_module.sleep(self._save_interval.total_seconds())
                    if self._should_save():
                        self._save_all()
                except Exception as e:
                    print(f"   ⚠️ 自動保存失敗: {e}")

        import threading

        self._save_thread = threading.Thread(target=auto_save_loop, daemon=True)
        self._save_thread.start()

    def _should_save(self) -> bool:
        """檢查是否應該保存"""
        # 如果有待重試的保存，縮短間隔
        if self._save_retry_pending:
            self._save_retry_pending = False
            return True
        return datetime.now() - self._last_save_time > self._save_interval

    def _save_all(self):
        """保存所有記憶數據"""
        with self._lock:
            try:
                self._save_agent_memories()
                self._save_conversations()
                self._save_ide_context()
                self._save_sessions()
                self._last_save_time = datetime.now()
                # 保存成功，重置失敗計數
                if self._save_failures > 0:
                    print(
                        f"   ✅ 記憶保存已恢復正常 (之前 {self._save_failures} 次失敗)"
                    )
                self._save_failures = 0
                self._last_save_error = None
                print(f"   💾 記憶已自動保存")
            except Exception as e:
                self._save_failures += 1
                self._last_save_error = str(e)
                print(
                    f"   ⚠️ 保存失敗 ({self._save_failures}/{self._max_save_failures}): {e}"
                )

                # 嘗試創建備份
                self._create_backup_on_failure()

                # 如果失敗次數過多，嘗試緊急保存
                if self._save_failures >= self._max_save_failures:
                    self._emergency_save()

    def _create_backup_on_failure(self):
        """保存失敗時創建緊急備份"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 備份智能體記憶
            if self._agent_memories:
                backup_file = (
                    self._backup_dir / f"agent_memories_backup_{timestamp}.json"
                )
                with open(backup_file, "w", encoding="utf-8") as f:
                    json.dump(self._agent_memories, f, ensure_ascii=False, indent=2)
                print(f"   📦 已創建記憶備份: {backup_file.name}")

            # 備份對話
            if self._conversations:
                backup_file = (
                    self._backup_dir / f"conversations_backup_{timestamp}.json"
                )
                with open(backup_file, "w", encoding="utf-8") as f:
                    json.dump(self._conversations, f, ensure_ascii=False, indent=2)
                print(f"   📦 已創建對話備份: {backup_file.name}")

            # 清理舊備份（保留最近10個）
            self._cleanup_old_backups()

        except Exception as backup_error:
            print(f"   ❌ 備份創建失敗: {backup_error}")

    def _cleanup_old_backups(self):
        """清理舊備份文件"""
        try:
            backup_files = sorted(
                self._backup_dir.glob("*.json"), key=lambda p: p.stat().st_mtime
            )
            # 保留最近20個備份
            for old_file in backup_files[:-20]:
                old_file.unlink()
        except Exception:
            pass  # 安靜失敗

    def _emergency_save(self):
        """緊急保存 - 嘗試逐個保存每個數據"""
        print(f"   🚨 執行緊急保存...")

        # 嘗試分别保存每個數據源
        emergency_methods = [
            ("智能體記憶", self._save_agent_memories, self.agent_memory_file),
            ("對話", self._save_conversations, self.conversation_file),
            ("IDE上下文", self._save_ide_context, self.ide_context_file),
            ("會話", self._save_sessions, self.session_file),
        ]

        for name, method, file_path in emergency_methods:
            try:
                method()
                print(f"   ✅ {name} 緊急保存成功")
            except Exception as e:
                print(f"   ❌ {name} 緊急保存失敗: {e}")

        # 標記需要重試
        self._save_retry_pending = True
        self._last_save_time = (
            datetime.now() - self._save_interval + timedelta(seconds=10)
        )  # 10秒後重試

    def get_save_status(self) -> Dict:
        """獲取保存狀態"""
        return {
            "last_save_time": self._last_save_time.isoformat()
            if self._last_save_time
            else None,
            "save_failures": self._save_failures,
            "max_failures": self._max_save_failures,
            "last_error": self._last_save_error,
            "retry_pending": self._save_retry_pending,
            "auto_save_enabled": self.auto_save,
        }

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        """Write JSON through a temp file so readers never see half-written data."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(
            f"{path.name}.tmp-{os.getpid()}-{threading.get_ident()}"
        )
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def _save_agent_memories(self):
        """保存智能體記憶"""
        self._atomic_write_json(self.agent_memory_file, self._agent_memories)

    def _save_conversations(self):
        """保存對話歷史"""
        self._atomic_write_json(self.conversation_file, self._conversations)

    def _save_ide_context(self):
        """保存IDE上下文"""
        self._atomic_write_json(self.ide_context_file, self._ide_context)

    def _save_sessions(self):
        """保存會話記錄"""
        self._atomic_write_json(self.session_file, self._sessions)

    # ==================== 智能體記憶 API ====================

    def save_agent_memory(
        self, agent_name: str, memory_data: Dict[str, Any], force_save: bool = False
    ):
        """
        保存智能體記憶

        Args:
            agent_name: 智能體名稱
            memory_data: 記憶數據
            force_save: 是否立即保存
        """
        with self._lock:
            if agent_name not in self._agent_memories:
                self._agent_memories[agent_name] = {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "memories": [],
                }

            memory_entry = {
                "timestamp": datetime.now().isoformat(),
                "data": memory_data,
            }

            self._agent_memories[agent_name]["memories"].append(memory_entry)
            self._agent_memories[agent_name]["last_updated"] = (
                datetime.now().isoformat()
            )

            # 只保留最近100條記憶
            if len(self._agent_memories[agent_name]["memories"]) > 100:
                self._agent_memories[agent_name]["memories"] = self._agent_memories[
                    agent_name
                ]["memaries"][-100:]

        if force_save:
            self._save_all()

    def get_agent_memory(self, agent_name: str, limit: int = None) -> List[Dict]:
        """
        獲取智能體記憶

        Args:
            agent_name: 智能體名稱
            limit: 返回數量限制

        Returns:
            記憶列表
        """
        memories = self._agent_memories.get(agent_name, {}).get("memories", [])
        if limit:
            return memories[-limit:]
        return memories

    def get_agent_preference(
        self, agent_name: str, key: str, default: Any = None
    ) -> Any:
        """獲取智能體偏好設置"""
        agent_data = self._agent_memories.get(agent_name, {})
        preferences = agent_data.get("preferences", {})
        return preferences.get(key, default)

    def set_agent_preference(
        self, agent_name: str, key: str, value: Any, force_save: bool = False
    ):
        """設置智能體偏好"""
        with self._lock:
            if agent_name not in self._agent_memories:
                self._agent_memories[agent_name] = {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "memories": [],
                    "preferences": {},
                }

            if "preferences" not in self._agent_memories[agent_name]:
                self._agent_memories[agent_name]["preferences"] = {}

            self._agent_memories[agent_name]["preferences"][key] = value
            self._agent_memories[agent_name]["last_updated"] = (
                datetime.now().isoformat()
            )

        if force_save:
            self._save_all()

    # ==================== 對話上下文 API ====================

    def save_conversation(
        self,
        agent_name: str,
        user_message: str,
        assistant_message: str,
        metadata: Dict = None,
        force_save: bool = False,
    ):
        """
        保存對話記錄

        Args:
            agent_name: 智能體名稱
            user_message: 用戶訊息
            assistant_message: 助手回覆
            metadata: 額外元數據
            force_save: 是否立即保存
        """
        with self._lock:
            # 創建對話ID
            conversation_id = self._generate_conversation_id(agent_name, user_message)

            if conversation_id not in self._conversations:
                self._conversations[conversation_id] = {
                    "agent_name": agent_name,
                    "created_at": datetime.now().isoformat(),
                    "last_message_at": datetime.now().isoformat(),
                    "messages": [],
                }

            message_entry = {
                "timestamp": datetime.now().isoformat(),
                "user": user_message,
                "assistant": assistant_message,
                "metadata": metadata or {},
            }

            self._conversations[conversation_id]["messages"].append(message_entry)
            self._conversations[conversation_id]["last_message_at"] = (
                datetime.now().isoformat()
            )

            # 只保留最近1000條對話
            if len(self._conversations) > 1000:
                # 刪除最舊的對話
                sorted_convs = sorted(
                    self._conversations.items(),
                    key=lambda x: x[1].get("last_message_at", ""),
                )
                for old_id, _ in sorted_convs[:100]:
                    del self._conversations[old_id]

        if force_save:
            self._save_all()

    def _generate_conversation_id(self, agent_name: str, message: str) -> str:
        """生成對話ID"""
        content = f"{agent_name}:{message[:50]}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def get_conversation_history(
        self, agent_name: str = None, limit: int = 50
    ) -> List[Dict]:
        """
        獲取對話歷史

        Args:
            agent_name: 智能體名稱（None=所有）
            limit: 返回數量限制

        Returns:
            對話歷史列表
        """
        if agent_name:
            convs = [
                c
                for c in self._conversations.values()
                if c.get("agent_name") == agent_name
            ]
        else:
            convs = list(self._conversations.values())

        # 按時間排序
        convs.sort(key=lambda x: x.get("last_message_at", ""), reverse=True)

        if limit:
            convs = convs[:limit]

        return convs

    def get_recent_messages(
        self, agent_name: str = None, message_limit: int = 20
    ) -> List[Dict]:
        """
        獲取最近的訊息（展平格式）

        Args:
            agent_name: 智能體名稱
            message_limit: 訊息數量限制

        Returns:
            訊息列表
        """
        all_messages = []

        for conv in self._conversations.values():
            if agent_name and conv.get("agent_name") != agent_name:
                continue
            all_messages.extend(conv.get("messages", []))

        # 按時間排序
        all_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if message_limit:
            all_messages = all_messages[:message_limit]

        return all_messages

    def search_conversations(self, query: str, agent_name: str = None) -> List[Dict]:
        """
        搜索對話

        Args:
            query: 搜索關鍵詞
            agent_name: 智能體名稱

        Returns:
            匹配的對話
        """
        results = []
        query_lower = query.lower()

        for conv in self._conversations.values():
            if agent_name and conv.get("agent_name") != agent_name:
                continue

            for msg in conv.get("messages", []):
                if (
                    query_lower in msg.get("user", "").lower()
                    or query_lower in msg.get("assistant", "").lower()
                ):
                    results.append(
                        {
                            "conversation_id": conv.get("id", ""),
                            "agent_name": conv.get("agent_name"),
                            "timestamp": msg.get("timestamp"),
                            "user": msg.get("user"),
                            "assistant": msg.get("assistant"),
                        }
                    )
                    break

        return results

    # ==================== IDE上下文 API ====================

    def save_ide_context(self, context_data: Dict[str, Any], force_save: bool = False):
        """
        保存IDE上下文

        Args:
            context_data: IDE上下文數據
            force_save: 是否立即保存
        """
        with self._lock:
            context_entry = {
                "timestamp": datetime.now().isoformat(),
                "data": context_data,
            }

            if "history" not in self._ide_context:
                self._ide_context["history"] = []

            self._ide_context["history"].append(context_entry)

            # 保留最新的上下文
            self._ide_context["latest"] = context_data
            self._ide_context["last_updated"] = datetime.now().isoformat()

            # 只保留最近50條歷史
            if len(self._ide_context["history"]) > 50:
                self._ide_context["history"] = self._ide_context["history"][-50:]

        if force_save:
            self._save_all()

    def get_ide_context(self) -> Dict:
        """獲取最新的IDE上下文"""
        return self._ide_context.get("latest", {})

    def get_ide_context_history(self, limit: int = 10) -> List[Dict]:
        """獲取IDE上下文歷史"""
        history = self._ide_context.get("history", [])
        if limit:
            return history[-limit:]
        return history

    def update_vscode_status(
        self, vscode_data: Dict[str, Any], force_save: bool = False
    ):
        """
        更新VSCode狀態

        Args:
            vscode_data: VSCode狀態數據
            force_save: 是否立即保存
        """
        with self._lock:
            if "vscode" not in self._ide_context:
                self._ide_context["vscode"] = {}

            self._ide_context["vscode"].update(vscode_data)
            self._ide_context["vscode"]["last_updated"] = datetime.now().isoformat()

        if force_save:
            self._save_all()

    def get_vscode_status(self) -> Dict:
        """獲取VSCode狀態"""
        return self._ide_context.get("vscode", {})

    def update_workspace_state(
        self, workspace_data: Dict[str, Any], force_save: bool = False
    ):
        """
        更新工作區狀態

        Args:
            workspace_data: 工作區數據
            force_save: 是否立即保存
        """
        with self._lock:
            if "workspace" not in self._ide_context:
                self._ide_context["workspace"] = {}

            self._ide_context["workspace"].update(workspace_data)
            self._ide_context["workspace"]["last_updated"] = datetime.now().isoformat()

        if force_save:
            self._save_all()

    def get_workspace_state(self) -> Dict:
        """獲取工作區狀態"""
        return self._ide_context.get("workspace", {})

    # ==================== 會話管理 API ====================

    def start_session(self, agent_name: str, session_data: Dict = None) -> str:
        """
        開始新會話

        Args:
            agent_name: 智能體名稱
            session_data: 初始會話數據

        Returns:
            會話ID
        """
        session_id = f"{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with self._lock:
            self._sessions[session_id] = {
                "id": session_id,
                "agent_name": agent_name,
                "started_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "data": session_data or {},
                "message_count": 0,
            }

        return session_id

    def update_session(self, session_id: str, message: str = None, data: Dict = None):
        """
        更新會話

        Args:
            session_id: 會話ID
            message: 新訊息
            data: 更新數據
        """
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["last_activity"] = datetime.now().isoformat()

                if message:
                    if "messages" not in self._sessions[session_id]:
                        self._sessions[session_id]["messages"] = []
                    self._sessions[session_id]["messages"].append(
                        {"timestamp": datetime.now().isoformat(), "content": message}
                    )
                    self._sessions[session_id]["message_count"] += 1

                if data:
                    self._sessions[session_id]["data"].update(data)

    def end_session(self, session_id: str):
        """結束會話"""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["ended_at"] = datetime.now().isoformat()

    def get_active_sessions(self) -> List[Dict]:
        """獲取活動會話"""
        active = []
        for session in self._sessions.values():
            if "ended_at" not in session:
                active.append(session)
        return active

    # ==================== 統一檢索 API ====================

    def search_all(self, query: str) -> Dict[str, List]:
        """
        統一搜索（搜索所有記憶）

        Args:
            query: 搜索關鍵詞

        Returns:
            搜索結果字典
        """
        results = {
            "conversations": self.search_conversations(query),
            "agent_memories": [],
            "ide_context": [],
        }

        # 搜索智能體記憶
        query_lower = query.lower()
        for agent_name, agent_data in self._agent_memories.items():
            for memory in agent_data.get("memories", []):
                memory_str = json.dumps(
                    memory.get("data", {}), ensure_ascii=False
                ).lower()
                if query_lower in memory_str:
                    results["agent_memories"].append(
                        {
                            "agent_name": agent_name,
                            "timestamp": memory.get("timestamp"),
                            "data": memory.get("data"),
                        }
                    )

        # 搜索IDE上下文
        context_str = json.dumps(self._ide_context, ensure_ascii=False).lower()
        if query_lower in context_str:
            results["ide_context"] = self._ide_context.get("history", [])[-5:]

        return results

    def get_full_context(self, agent_name: str = None) -> str:
        """
        獲取完整上下文文本（用於填充AI提示）

        Args:
            agent_name: 智能體名稱

        Returns:
            格式化的上下文字符串
        """
        context_parts = []

        # 1. 添加最近的對話
        recent_messages = self.get_recent_messages(
            agent_name=agent_name, message_limit=10
        )
        if recent_messages:
            context_parts.append("=== 最近對話 ===")
            for msg in reversed(recent_messages):
                context_parts.append(f"用戶: {msg.get('user', '')}")
                context_parts.append(f"助手: {msg.get('assistant', '')}")
                context_parts.append("")

        # 2. 添加IDE上下文
        ide_context = self.get_ide_context()
        if ide_context:
            context_parts.append("=== IDE上下文 ===")
            context_parts.append(json.dumps(ide_context, ensure_ascii=False, indent=2))
            context_parts.append("")

        # 3. 添加智能體記憶
        if agent_name:
            memories = self.get_agent_memory(agent_name, limit=5)
            if memories:
                context_parts.append("=== 智能體記憶 ===")
                for mem in reversed(memories):
                    context_parts.append(
                        f"[{mem.get('timestamp', '')}] {json.dumps(mem.get('data', {}), ensure_ascii=False)}"
                    )
                context_parts.append("")

        return "\n".join(context_parts)

    def force_save(self):
        """強制保存所有數據"""
        self._save_all()

    def clear_old_data(self, days: int = 30):
        """
        清理舊數據

        Args:
            days: 保留天數
        """
        with self._lock:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            # 清理對話
            for conv_id in list(self._conversations.keys()):
                last_time = self._conversations[conv_id].get("last_message_at", "")
                if last_time < cutoff_iso:
                    del self._conversations[conv_id]

            # 清理會話
            for session_id in list(self._sessions.keys()):
                last_activity = self._sessions[session_id].get("last_activity", "")
                if last_activity < cutoff_iso:
                    del self._sessions[session_id]

            # 清理IDE上下文歷史
            if "history" in self._ide_context:
                self._ide_context["history"] = [
                    h
                    for h in self._ide_context["history"]
                    if h.get("timestamp", "") >= cutoff_iso
                ]

        self._save_all()
        print(f"✅ 已清理 {days} 天前的舊數據")


# 便捷函數
_default_manager = None


def get_memory_manager(base_dir: str = None) -> AgentMemoryManager:
    """獲取默認的記憶管理器實例"""
    global _default_manager
    if _default_manager is None:
        base_dir = base_dir or str(Path(__file__).resolve().parents[1])
        _default_manager = AgentMemoryManager(base_dir)
    return _default_manager

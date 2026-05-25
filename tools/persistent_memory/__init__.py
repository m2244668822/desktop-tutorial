#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化記憶系統 - 主管理器
Persistent Memory System - Main Manager

功能：
- 整合所有子模組
- 提供統一 API
- 管理生命週期

作者：AI 智能體
創建時間：2026-03-21
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# 導入子模組
from .database_schema import create_tables, init_database
from .storage_manager import StorageManager, create_storage_manager
from .crypto_manager import CryptoManager, KeyManager
from .state_restorer import StateRestorer
from .desktop_integration import (
    DesktopIntegration,
    IntegrationConfig,
    create_desktop_integration,
    DesktopIntegrationContext,
)
from .desktop_launcher import (
    DesktopLauncher,
    PluginManager,
    WindowManager,
    create_launcher,
)
from .vscode_protocol import (
    VSCodeProtocol,
    StdioProtocol,
    WebSocketProtocol,
    create_stdio_protocol,
    create_ws_protocol,
)


# 統一記憶體管理器 API
class PersistentMemoryManager:
    """
    統一持久化記憶管理器
    整合所有子模組，提供統一的 API 介面
    """

    def __init__(
        self, db_path: str = "data/persistent_memory.db", encryption_key: bytes = None
    ):
        self.db_path = db_path
        self._storage = None
        self._crypto = None
        self._restorer = None
        self._conversation = None
        self._agent_state = None
        self._task_tracker = None
        self._quick_reply = None
        self._initialized = False
        self._encryption_key = encryption_key

    async def initialize(self):
        """初始化所有子模組"""
        if self._initialized:
            return

        # 建立數據庫表
        await create_tables(self.db_path)

        # 初始化儲存管理器
        self._storage = await create_storage_manager(self.db_path)

        # 初始化加密管理器
        self._crypto = CryptoManager(self._encryption_key)

        # 初始化狀態恢復器
        self._restorer = StateRestorer(self._storage)

        # 初始化對話管理器
        self._conversation = ConversationManager(self._storage)

        # 初始化智能體狀態管理器
        self._agent_state = AgentStateManager(self._storage)

        # 初始化任務追蹤器
        self._task_tracker = TaskTracker(self._storage)

        # 初始化快速回覆引擎
        self._quick_reply = QuickReplyEngine(self._storage)

        self._initialized = True

    @property
    def conversation(self) -> ConversationManager:
        """對話管理器"""
        return self._conversation

    @property
    def agent_state(self) -> AgentStateManager:
        """智能體狀態管理器"""
        return self._agent_state

    @property
    def task_tracker(self) -> TaskTracker:
        """任務追蹤器"""
        return self._task_tracker

    @property
    def quick_reply(self) -> QuickReplyEngine:
        """快速回覆引擎"""
        return self._quick_reply

    async def restore_state(self):
        """恢復上次工作狀態"""
        return await self._restorer.restore()

    async def save_current_state(self, state: dict):
        """保存當前工作狀態"""
        await self._restorer.save(state)

    async def close(self):
        """關閉並保存所有數據"""
        if self._storage:
            await self._storage.close()
        self._initialized = False


async def create_memory_manager(
    db_path: str = "data/persistent_memory.db", encryption_key: bytes = None
) -> PersistentMemoryManager:
    """
    建立持久化記憶管理器工廠函數

    Args:
        db_path: SQLite 資料庫路徑
        encryption_key: 加密金鑰（可選）

    Returns:
        PersistentMemoryManager 實例

    Example:
        ```python
        manager = await create_memory_manager(
            db_path="data/persistent_memory.db"
        )

        # 創建對話
        session_id = await manager.conversation.create_session("新對話")

        # 添加訊息
        await manager.conversation.add_message(
            session_id, "user", "你好"
        )

        # 獲取對話
        session = manager.conversation.get_session(session_id)

        # 關閉
        await manager.close()
        ```
    """
    manager = PersistentMemoryManager(db_path, encryption_key)
    await manager.initialize()
    return manager


__all__ = [
    # 基礎類別
    "PersistentMemoryManager",
    "PersistentMemoryConfig",
    # 工廠函數
    "create_memory_manager",
    "create_storage_manager",
    "create_launcher",
    "create_stdio_protocol",
    "create_ws_protocol",
    "create_desktop_integration",
    # 子模組類別
    "StorageManager",
    "CryptoManager",
    "KeyManager",
    "StateRestorer",
    "ConversationManager",
    "AgentStateManager",
    "TaskTracker",
    "QuickReplyEngine",
    "DesktopLauncher",
    "PluginManager",
    "WindowManager",
    "VSCodeProtocol",
    "StdioProtocol",
    "WebSocketProtocol",
    "DesktopIntegration",
    "IntegrationConfig",
    "DesktopIntegrationContext",
    # 資料庫函數
    "create_tables",
    "init_database",
]

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 配置類別
# ============================================================


@dataclass
class PersistentMemoryConfig:
    """持久化記憶配置"""

    db_path: str = "data/persistent_memory.db"
    enable_encryption: bool = True
    encryption_password: Optional[str] = None
    min_flush_size: int = 256 * 1024
    max_flush_size: int = 1024 * 1024
    flush_interval: float = 3.0
    max_inactive_hours: int = 24
    auto_cleanup_days: int = 30
    enable_cache: bool = True
    cache_ttl: int = 300
    max_version_count: int = 50


# ============================================================
# 主管理器類
# ============================================================


class PersistentMemoryManager:
    """
    持久化記憶系統主管理器

    功能：
    - 會話管理（創建、讀取、更新、刪除）
    - 訊息持久化
    - 智能體狀態追蹤
    - 任務管理
    - 快速回覆
    - 自動備份和恢復
    - 加密支援

    使用範例：
        # 初始化
        manager = PersistentMemoryManager()
        await manager.initialize()

        # 創建會話
        session_id = await manager.create_session("新對話")

        # 發送訊息
        await manager.add_message(session_id, "user", "你好")

        # 取得會話
        session = manager.get_session(session_id)

        # 關閉
        await manager.close()
    """

    def __init__(self, config: Optional[PersistentMemoryConfig] = None):
        """
        初始化持久化記憶管理器

        Args:
            config: 配置物件
        """
        self.config = config or PersistentMemoryConfig()

        # 子系統
        self.storage: Optional[StorageManager] = None
        self.crypto: Optional[CryptoManager] = None
        self.key_manager: Optional[KeyManager] = None
        self.restorer: Optional[StateRestorer] = None

        # 狀態
        self._initialized = False
        self._session_context: Dict[str, Any] = {}

    async def initialize(self) -> bool:
        """
        初始化持久化記憶系統

        Returns:
            是否成功
        """
        if self._initialized:
            logger.warning("持久化記憶系統已經初始化")
            return True

        try:
            # 確保目錄存在
            db_dir = os.path.dirname(self.config.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # 初始化資料庫
            init_database(self.config.db_path)

            # 初始化儲存管理器
            self.storage = await create_storage_manager(self.config.db_path)

            # 初始化加密管理器
            if self.config.enable_encryption:
                self.crypto = CryptoManager()
                self.key_manager = KeyManager(
                    storage_path=os.path.join(
                        os.path.dirname(self.config.db_path), "keys"
                    )
                )

            # 初始化狀態恢復管理器
            self.restorer = StateRestorer(
                self.storage,
                max_inactive_hours=self.config.max_inactive_hours,
                auto_cleanup_days=self.config.auto_cleanup_days,
            )
            self.restorer.enable_cache(self.config.enable_cache)
            self.restorer.set_cache_ttl(self.config.cache_ttl)

            # 恢復之前的狀態
            await self._restore_previous_state()

            self._initialized = True
            logger.info("持久化記憶系統初始化完成")

            return True

        except Exception as e:
            logger.error(f"初始化失敗: {e}")
            return False

    async def _restore_previous_state(self):
        """恢復之前的狀態"""
        if not self.restorer:
            return

        # 恢復未完成的會話
        result = self.restorer.restore_all_unfinished()

        if result.restored_items:
            self._session_context = result.restored_data
            logger.info(f"恢復了 {len(result.restored_items)} 個項目")

    # ==========================
    # 會話管理
    # ==========================

    async def create_session(
        self, title: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        創建新會話

        Args:
            title: 會話標題
            context: 初始上下文資料

        Returns:
            會話 ID
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        session_id = self._generate_id("session")
        now = datetime.now().isoformat()

        await self.storage.async_write(
            "sessions",
            {
                "session_id": session_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "is_active": 1,
                "message_count": 0,
                "context_data": json.dumps(context or {}, ensure_ascii=False),
            },
            priority=10,
            operation_type="insert",
        )

        # 初始化任務追蹤
        await self.storage.async_write(
            "tasks",
            {
                "task_id": session_id,
                "task_name": title,
                "status": "in_progress",
                "progress": 0.0,
                "created_at": now,
                "updated_at": now,
                "session_id": session_id,
            },
            priority=5,
        )

        logger.info(f"創建會話: {session_id} - {title}")

        return session_id

    async def close_session(self, session_id: str):
        """
        關閉會話

        Args:
            session_id: 會話 ID
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        now = datetime.now().isoformat()

        await self.storage.async_write(
            "sessions",
            {"session_id": session_id, "updated_at": now, "is_active": 0},
            priority=10,
            operation_type="update",
        )

        # 更新任務狀態
        await self.storage.async_write(
            "tasks",
            {
                "task_id": session_id,
                "status": "completed",
                "progress": 100.0,
                "updated_at": now,
            },
            priority=5,
            operation_type="update",
        )

        logger.info(f"關閉會話: {session_id}")

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        添加訊息

        Args:
            session_id: 會話 ID
            role: 角色 (user/assistant/system)
            content: 訊息內容
            metadata: 額外資料

        Returns:
            訊息 ID
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        message_id = self._generate_id("msg")
        now = datetime.now().isoformat()

        # 加密內容（如果啟用）
        if self.config.enable_encryption and self.config.encryption_password:
            content = self.crypto.encrypt_dict(
                {"content": content}, self.config.encryption_password
            )

        # 寫入訊息
        await self.storage.async_write(
            "messages",
            {
                "message_id": message_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "created_at": now,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            },
            priority=5,
        )

        # 更新會話計數
        sessions = self.storage.read("sessions", conditions={"session_id": session_id})

        if sessions:
            message_count = sessions[0].get("message_count", 0) + 1
            await self.storage.async_write(
                "sessions",
                {
                    "session_id": session_id,
                    "updated_at": now,
                    "message_count": message_count,
                },
                priority=3,
                operation_type="update",
            )

        return message_id

    def get_session(
        self, session_id: str, include_messages: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        取得會話

        Args:
            session_id: 會話 ID
            include_messages: 是否包含訊息

        Returns:
            會話資料
        """
        if not self.restorer:
            return None

        return self.restorer.restore_session(session_id, include_messages)

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        取得活動會話列表

        Returns:
            會話列表
        """
        if not self.restorer:
            return []

        return [
            {
                "session_id": s.session_id,
                "title": s.title,
                "message_count": s.message_count,
                "updated_at": s.updated_at,
            }
            for s in self.restorer.get_unfinished_sessions()
        ]

    async def update_session_context(self, session_id: str, context: Dict[str, Any]):
        """
        更新會話上下文

        Args:
            session_id: 會話 ID
            context: 上下文資料
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        now = datetime.now().isoformat()

        await self.storage.async_write(
            "sessions",
            {
                "session_id": session_id,
                "updated_at": now,
                "context_data": json.dumps(context, ensure_ascii=False),
            },
            priority=5,
            operation_type="update",
        )

    # ==========================
    # 智能體狀態管理
    # ==========================

    async def save_agent_state(
        self,
        agent_id: str,
        state_name: str,
        data: Dict[str, Any],
        create_version: bool = True,
    ):
        """
        保存智能體狀態

        Args:
            agent_id: 智能體 ID
            state_name: 狀態名稱
            data: 狀態資料
            create_version: 是否創建版本
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        state_id = self._generate_id("state")
        now = datetime.now().isoformat()

        # 獲取當前版本號
        version = 1
        if create_version:
            existing = self.storage.read(
                "agent_states",
                conditions={"agent_id": agent_id, "state_name": state_name},
                order_by="version DESC",
                limit=1,
            )
            if existing:
                version = existing[0].get("version", 0) + 1

        # 檢查版本數量限制
        if self.config.max_version_count > 0:
            await self._cleanup_old_versions(agent_id, state_name)

        # 加密資料（如果啟用）
        state_data = data
        if self.config.enable_encryption and self.config.encryption_password:
            state_data = {
                "encrypted": self.crypto.encrypt_dict(
                    data, self.config.encryption_password
                )
            }

        await self.storage.async_write(
            "agent_states",
            {
                "state_id": state_id,
                "agent_id": agent_id,
                "state_name": state_name,
                "data": json.dumps(state_data, ensure_ascii=False),
                "version": version,
                "created_at": now,
            },
            priority=8,
        )

        logger.info(f"保存智能體狀態: {agent_id}/{state_name} v{version}")

    async def _cleanup_old_versions(self, agent_id: str, state_name: str):
        """清理舊版本"""
        if not self.storage:
            return

        # 獲取所有版本
        versions = self.storage.read(
            "agent_states",
            conditions={"agent_id": agent_id, "state_name": state_name},
            order_by="created_at DESC",
        )

        # 超過限制則刪除舊版本
        if len(versions) > self.config.max_version_count:
            to_delete = versions[self.config.max_version_count :]
            for v in to_delete:
                self.storage.write(
                    "agent_states", {"state_id": v["state_id"]}, operation_type="delete"
                )

    def get_agent_state(
        self,
        agent_id: str,
        state_name: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        取得智能體狀態

        Args:
            agent_id: 智能體 ID
            state_name: 狀態名稱
            version: 版本號

        Returns:
            狀態資料
        """
        if not self.restorer:
            return None

        return self.restorer.restore_agent_state(agent_id, version)

    # ==========================
    # 任務管理
    # ==========================

    async def create_task(
        self,
        task_name: str,
        description: Optional[str] = None,
        due_date: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        創建任務

        Args:
            task_name: 任務名稱
            description: 描述
            due_date: 截止日期
            session_id: 相關會話 ID

        Returns:
            任務 ID
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        task_id = self._generate_id("task")
        now = datetime.now().isoformat()

        await self.storage.async_write(
            "tasks",
            {
                "task_id": task_id,
                "task_name": task_name,
                "description": description or "",
                "status": "pending",
                "progress": 0.0,
                "created_at": now,
                "updated_at": now,
                "due_date": due_date,
                "session_id": session_id,
            },
            priority=7,
        )

        logger.info(f"創建任務: {task_id} - {task_name}")

        return task_id

    async def update_task_progress(
        self, task_id: str, progress: float, status: Optional[str] = None
    ):
        """
        更新任務進度

        Args:
            task_id: 任務 ID
            progress: 進度 (0-100)
            status: 狀態
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        now = datetime.now().isoformat()

        update_data = {
            "task_id": task_id,
            "progress": min(max(progress, 0), 100),
            "updated_at": now,
        }

        if status:
            update_data["status"] = status

        await self.storage.async_write(
            "tasks", update_data, priority=6, operation_type="update"
        )

    def get_tasks(
        self, status_filter: Optional[str] = None, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        取得任務列表

        Args:
            status_filter: 狀態過濾
            session_id: 會話 ID 過濾

        Returns:
            任務列表
        """
        if not self.restorer:
            return []

        conditions = {}
        if status_filter:
            conditions["status"] = status_filter
        if session_id:
            conditions["session_id"] = session_id

        tasks = self.storage.read(
            "tasks",
            conditions=conditions if conditions else None,
            order_by="updated_at DESC",
        )

        return [
            {
                "task_id": t["task_id"],
                "task_name": t.get("task_name", ""),
                "status": t.get("status", "pending"),
                "progress": t.get("progress", 0.0),
                "due_date": t.get("due_date"),
                "created_at": t.get("created_at"),
                "updated_at": t.get("updated_at"),
            }
            for t in tasks
        ]

    # ==========================
    # 快速回覆管理
    # ==========================

    async def add_quick_reply(
        self, shortcut: str, response: str, category: str = "general"
    ):
        """
        添加快速回覆

        Args:
            shortcut: 捷徑
            response: 回覆內容
            category: 分類
        """
        if not self.storage:
            raise RuntimeError("系統未初始化")

        reply_id = self._generate_id("reply")
        now = datetime.now().isoformat()

        await self.storage.async_write(
            "quick_replies",
            {
                "reply_id": reply_id,
                "shortcut": shortcut,
                "response": response,
                "category": category,
                "created_at": now,
                "usage_count": 0,
            },
            priority=4,
        )

    def get_quick_replies(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        取得快速回覆

        Args:
            category: 分類過濾

        Returns:
            快速回覆列表
        """
        conditions = {}
        if category:
            conditions["category"] = category

        replies = self.storage.read(
            "quick_replies",
            conditions=conditions if conditions else None,
            order_by="usage_count DESC",
        )

        return [
            {
                "shortcut": r["shortcut"],
                "response": r.get("response", ""),
                "category": r.get("category", ""),
                "usage_count": r.get("usage_count", 0),
            }
            for r in replies
        ]

    async def increment_reply_usage(self, shortcut: str):
        """
        增加快速回覆使用次數

        Args:
            shortcut: 捷徑
        """
        if not self.storage:
            return

        replies = self.storage.read("quick_replies", conditions={"shortcut": shortcut})

        if replies:
            current_count = replies[0].get("usage_count", 0)
            await self.storage.async_write(
                "quick_replies",
                {"reply_id": replies[0]["reply_id"], "usage_count": current_count + 1},
                priority=2,
                operation_type="update",
            )

    def find_quick_reply(self, input_text: str) -> Optional[str]:
        """
        尋找匹配的快速回覆

        Args:
            input_text: 輸入文字

        Returns:
            匹配的回覆，若無則返回 None
        """
        replies = self.get_quick_replies()

        # 精確匹配
        for reply in replies:
            if reply["shortcut"] == input_text:
                return reply["response"]

        # 前綴匹配
        for reply in replies:
            if input_text.startswith(reply["shortcut"]):
                return reply["response"]

        return None

    # ==========================
    # 系統功能
    # ==========================

    def export_tasks_csv(self, output_path: str) -> str:
        """
        匯出任務為 CSV

        Args:
            output_path: 輸出路徑

        Returns:
            輸出路徑
        """
        if not self.restorer:
            raise RuntimeError("系統未初始化")

        return self.restorer.export_tasks_csv(output_path)

    async def restore_all(self) -> Dict[str, Any]:
        """
        恢復所有資料

        Returns:
            恢復結果
        """
        if not self.restorer:
            raise RuntimeError("系統未初始化")

        return self.restorer.restore_all().__dict__

    def get_statistics(self) -> Dict[str, Any]:
        """
        取得統計資訊

        Returns:
            統計資料
        """
        if not self.storage:
            return {}

        stats = self.storage.get_stats()

        # 計算會話數量
        sessions = self.storage.read("sessions")
        active_sessions = len([s for s in sessions if s.get("is_active") == 1])

        # 計算訊息數量
        messages = self.storage.read("messages")

        # 計算任務數量
        tasks = self.storage.read("tasks")

        return {
            "total_sessions": len(sessions),
            "active_sessions": active_sessions,
            "total_messages": len(messages),
            "total_tasks": len(tasks),
            "storage_stats": stats.__dict__,
            "database_size": self.storage.get_size(),
        }

    def clear_cache(self):
        """清除快取"""
        if self.restorer:
            self.restorer.clear_cache()

    async def close(self):
        """關閉系統"""
        if self.storage:
            await self.storage.close()

        self._initialized = False
        logger.info("持久化記憶系統已關閉")

    def _generate_id(self, prefix: str) -> str:
        """生成唯一 ID"""
        import time
        import random

        timestamp = int(time.time() * 1000)
        random_part = random.randint(1000, 9999)
        return f"{prefix}_{timestamp}_{random_part}"


# ============================================================
# 便捷函數
# ============================================================


async def create_memory_manager(
    db_path: str = "data/persistent_memory.db",
    enable_encryption: bool = True,
    password: Optional[str] = None,
) -> PersistentMemoryManager:
    """
    建立並初始化記憶管理器的便捷函數

    Args:
        db_path: 資料庫路徑
        enable_encryption: 啟用加密
        password: 加密密碼

    Returns:
        初始化的 PersistentMemoryManager
    """
    config = PersistentMemoryConfig(
        db_path=db_path,
        enable_encryption=enable_encryption,
        encryption_password=password,
    )

    manager = PersistentMemoryManager(config)
    await manager.initialize()

    return manager


# ============================================================
# 使用範例
# ============================================================


async def main():
    """使用範例"""
    # 建立記憶管理器
    manager = await create_memory_manager(
        db_path="data/persistent_memory.db",
        enable_encryption=False,  # 測試時停用加密
    )

    # 創建會話
    session_id = await manager.create_session("測試對話")
    print(f"創建會話: {session_id}")

    # 發送訊息
    await manager.add_message(session_id, "user", "你好，這是測試訊息")
    await manager.add_message(session_id, "assistant", "你好！我收到你的訊息了。")

    # 取得會話
    session = manager.get_session(session_id)
    print(f"會話訊息數: {len(session.get('messages', []))}")

    # 取得活動會話
    active = manager.get_active_sessions()
    print(f"活動會話數: {len(active)}")

    # 創建任務
    task_id = await manager.create_task("完成報告", due_date="2026-03-31")
    await manager.update_task_progress(task_id, 50)
    print(f"任務進度: 50%")

    # 添加快速回覆
    await manager.add_quick_reply("/help", "這是幫助訊息", "system")

    # 取得統計
    stats = manager.get_statistics()
    print(f"總會話數: {stats['total_sessions']}")
    print(f"總訊息數: {stats['total_messages']}")
    print(f"資料庫大小: {stats['database_size']} bytes")

    # 關閉
    await manager.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面應用程式整合模組
Desktop Application Integration Module

功能：
- 與桌面軟體 (desktop_chat_app.py) 整合
- 自動初始化持久化記憶系統
- 對話上下文自動恢復
- 事件驅動的數據同步

作者：AI 智能體
創建時間：2026-03-21
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable, Type

# 導入持久化記憶系統
from . import PersistentMemoryManager, create_memory_manager, PersistentMemoryConfig

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 整合配置
# ============================================================


@dataclass
class IntegrationConfig:
    """整合配置"""

    # 資料庫路徑
    db_path: str = "data/persistent_memory.db"

    # 自動保存間隔（秒）
    auto_save_interval: float = 3.0

    # 緩衝區大小（位元組）
    buffer_size: int = 512 * 1024  # 512KB

    # 自動恢復
    auto_restore: bool = True

    # 最大恢復對話數
    max_restore_sessions: int = 10

    # 加密啟用
    encryption_enabled: bool = True

    # 日誌級別
    log_level: int = logging.INFO

    # 調試模式
    debug_mode: bool = False


@dataclass
class SessionContext:
    """對話上下文"""

    session_id: str
    title: str
    created_at: str
    last_active: str
    message_count: int = 0
    context_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApplicationState:
    """應用程式狀態"""

    running: bool = False
    initialized: bool = False
    session_id: Optional[str] = None
    last_error: Optional[str] = None
    startup_time: Optional[str] = None


# ============================================================
# 桌面整合器
# ============================================================


class DesktopIntegration:
    """
    桌面應用程式整合器

    功能：
    - 初始化持久化記憶系統
    - 對話管理
    - 上下文恢復
    - 事件處理
    """

    def __init__(self, config: IntegrationConfig = None):
        self.config = config or IntegrationConfig()

        # 持久化記憶系統
        self.memory_manager: Optional[PersistentMemoryManager] = None

        # 應用程式狀態
        self.state = ApplicationState()

        # 回調函數
        self._callbacks: Dict[str, List[Callable]] = {
            "on_session_created": [],
            "on_message_sent": [],
            "on_message_received": [],
            "on_context_restored": [],
            "on_error": [],
            "on_state_changed": [],
        }

        # 對話歷史緩衝
        self._message_buffer: List[Dict[str, Any]] = []

        # 運行任務
        self._running_tasks: List[asyncio.Task] = []

    async def initialize(self) -> bool:
        """
        初始化整合器

        Returns:
            是否初始化成功
        """
        try:
            logger.info("正在初始化桌面整合器...")

            # 創建資料庫目錄
            db_dir = Path(self.config.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

            # 配置持久化記憶系統
            # 使用統一的 PersistentMemoryConfig
            config = PersistentMemoryConfig(
                db_path=self.config.db_path,
                enable_encryption=self.config.encryption_enabled,
                encryption_password=getattr(self.config, "encryption_password", None),
                flush_interval=self.config.auto_save_interval,
                min_flush_size=self.config.buffer_size,
            )

            # 創建持久化記憶管理器
            self.memory_manager = await create_memory_manager(
                db_path=config.db_path,
                enable_encryption=config.enable_encryption,
                password=config.encryption_password,
            )

            # 如果啟用自動恢復，嘗試恢復之前的對話
            if self.config.auto_restore:
                restored = await self._restore_previous_sessions()
                if restored:
                    logger.info(f"已恢復 {len(restored)} 個對話會話")
                    await self._notify("on_context_restored", restored)

            # 標記為已初始化
            self.state.initialized = True
            self.state.running = True
            self.state.startup_time = datetime.now().isoformat()

            # 啟動後台任務
            await self._start_background_tasks()

            logger.info("桌面整合器初始化完成")
            return True

        except Exception as e:
            logger.error(f"初始化失敗: {e}")
            self.state.last_error = str(e)
            await self._notify("on_error", str(e))
            return False

    async def shutdown(self):
        """關閉整合器"""
        logger.info("正在關閉桌面整合器...")

        # 取消後台任務
        for task in self._running_tasks:
            task.cancel()

        # 等待任務完成
        await asyncio.gather(*self._running_tasks, return_exceptions=True)
        self._running_tasks.clear()

        # 關閉記憶管理器
        if self.memory_manager:
            await self.memory_manager.close()

        self.state.running = False
        logger.info("桌面整合器已關閉")

    async def create_session(self, title: str = "新對話") -> str:
        """
        創建新對話會話

        Args:
            title: 對話標題

        Returns:
            會話 ID
        """
        if not self.memory_manager:
            raise RuntimeError("記憶管理器未初始化")

        # 創建會話
        session_id = await self.memory_manager.create_session(title)

        # 更新狀態
        self.state.session_id = session_id

        # 通知回調
        await self._notify(
            "on_session_created", {"session_id": session_id, "title": title}
        )

        logger.info(f"創建新對話會話: {session_id}")
        return session_id

    async def send_message(
        self, content: str, role: str = "user", metadata: Dict[str, Any] = None
    ) -> str:
        """
        發送訊息

        Args:
            content: 訊息內容
            role: 角色 (user/assistant/system)
            metadata: 額外元數據

        Returns:
            訊息 ID
        """
        if not self.memory_manager:
            raise RuntimeError("記憶管理器未初始化")

        # 獲取當前會話
        if not self.state.session_id:
            await self.create_session("新對話")

        # 添加訊息
        message_id = await self.memory_manager.add_message(
            self.state.session_id, role, content, metadata or {}
        )

        # 更新緩衝
        self._message_buffer.append(
            {
                "id": message_id,
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # 限制緩衝大小
        if len(self._message_buffer) > 100:
            self._message_buffer = self._message_buffer[-100:]

        # 通知回調
        await self._notify(
            "on_message_sent",
            {
                "session_id": self.state.session_id,
                "message_id": message_id,
                "role": role,
                "content": content,
            },
        )

        return message_id

    async def receive_response(
        self, content: str, metadata: Dict[str, Any] = None
    ) -> str:
        """
        接收回應

        Args:
            content: 回應內容
            metadata: 額外元數據

        Returns:
            訊息 ID
        """
        return await self.send_message(
            content=content, role="assistant", metadata=metadata
        )

    async def get_session_history(
        self, session_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        獲取對話歷史

        Args:
            session_id: 會話 ID（預設當前會話）
            limit: 限制數量

        Returns:
            訊息列表
        """
        if not self.memory_manager:
            return []

        session_id = session_id or self.state.session_id
        if not session_id:
            return []

        return await self.memory_manager.get_messages(session_id, limit)

    async def list_sessions(self, limit: int = 50) -> List[SessionContext]:
        """
        列出所有對話會話

        Args:
            limit: 限制數量

        Returns:
            會話列表
        """
        if not self.memory_manager:
            return []

        sessions = await self.memory_manager.list_sessions(limit)

        return [
            SessionContext(
                session_id=s["session_id"],
                title=s.get("title", "無標題"),
                created_at=s.get("created_at", ""),
                last_active=s.get("last_active", ""),
                message_count=s.get("message_count", 0),
                context_data=s.get("context_data", {}),
            )
            for s in sessions
        ]

    async def delete_session(self, session_id: str) -> bool:
        """
        刪除對話會話

        Args:
            session_id: 會話 ID

        Returns:
            是否成功
        """
        if not self.memory_manager:
            return False

        return await self.memory_manager.delete_session(session_id)

    async def save_agent_state(
        self, agent_id: str, state: Dict[str, Any], metadata: Dict[str, Any] = None
    ) -> bool:
        """
        保存智能體狀態

        Args:
            agent_id: 智能體 ID
            state: 狀態數據
            metadata: 額外元數據

        Returns:
            是否成功
        """
        if not self.memory_manager:
            return False

        return await self.memory_manager.save_agent_state(
            agent_id, state, metadata or {}
        )

    async def load_agent_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        載入智能體狀態

        Args:
            agent_id: 智能體 ID

        Returns:
            狀態數據
        """
        if not self.memory_manager:
            return None

        return await self.memory_manager.load_agent_state(agent_id)

    async def create_task(
        self,
        title: str,
        description: str = "",
        priority: int = 0,
        due_date: Optional[str] = None,
    ) -> str:
        """
        創建任務

        Args:
            title: 任務標題
            description: 任務描述
            priority: 優先級 (0-9)
            due_date: 截止日期

        Returns:
            任務 ID
        """
        if not self.memory_manager:
            raise RuntimeError("記憶管理器未初始化")

        return await self.memory_manager.create_task(
            title=title, description=description, priority=priority, due_date=due_date
        )

    async def update_task_progress(
        self, task_id: str, progress: int, notes: str = ""
    ) -> bool:
        """
        更新任務進度

        Args:
            task_id: 任務 ID
            progress: 進度 (0-100)
            notes: 備註

        Returns:
            是否成功
        """
        if not self.memory_manager:
            return False

        return await self.memory_manager.update_task_progress(task_id, progress, notes)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        列出任務

        Args:
            status: 狀態過濾
            priority: 優先級過濾
            from_date: 開始日期過濾
            to_date: 結束日期過濾
            limit: 限制數量

        Returns:
            任務列表
        """
        if not self.memory_manager:
            return []

        return await self.memory_manager.list_tasks(
            status=status,
            priority=priority,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )

    async def export_tasks_csv(self, file_path: str) -> bool:
        """
        導出任務為 CSV

        Args:
            file_path: 輸出檔案路徑

        Returns:
            是否成功
        """
        if not self.memory_manager:
            return False

        tasks = await self.memory_manager.list_tasks(limit=10000)

        if not tasks:
            return False

        # 生成 CSV
        import csv

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            if tasks:
                writer = csv.DictWriter(f, fieldnames=tasks[0].keys())
                writer.writeheader()
                writer.writerows(tasks)

        logger.info(f"任務已導出至: {file_path}")
        return True

    async def suggest_quick_reply(
        self, context: str, max_suggestions: int = 5
    ) -> List[str]:
        """
        建議快速回覆

        Args:
            context: 上下文
            max_suggestions: 最大建議數

        Returns:
            建議列表
        """
        if not self.memory_manager:
            return []

        return await self.memory_manager.suggest_replies(context, max_suggestions)

    async def add_quick_reply(
        self, trigger: str, response: str, category: str = "預設"
    ) -> bool:
        """
        添加快速回覆

        Args:
            trigger: 觸發詞
            response: 回覆內容
            category: 分類

        Returns:
            是否成功
        """
        if not self.memory_manager:
            return False

        return await self.memory_manager.add_quick_reply(trigger, response, category)

    def register_callback(self, event: str, callback: Callable):
        """
        註冊回調

        Args:
            event: 事件名稱
            callback: 回調函數
        """
        if event not in self._callbacks:
            self._callbacks[event] = []

        self._callbacks[event].append(callback)

    def unregister_callback(self, event: str, callback: Callable):
        """
        取消註冊回調

        Args:
            event: 事件名稱
            callback: 回調函數
        """
        if event in self._callbacks:
            self._callbacks[event].remove(callback)

    async def _notify(self, event: str, data: Any):
        """觸發事件通知"""
        callbacks = self._callbacks.get(event, [])

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"回調執行失敗: {event} - {e}")

    async def _restore_previous_sessions(self) -> List[Dict[str, Any]]:
        """恢復之前的對話會話"""
        if not self.memory_manager:
            return []

        # 獲取未完成的會話
        sessions = await self.memory_manager.list_sessions(
            self.config.max_restore_sessions
        )

        restored = []

        for session in sessions:
            # 檢查是否有未完成的對話
            messages = await self.memory_manager.get_messages(
                session["session_id"], limit=1
            )

            if messages:
                restored.append(session)
                logger.info(f"恢復會話: {session['session_id']}")

        return restored

    async def _start_background_tasks(self):
        """啟動後台任務"""
        # 定期保存任務
        task = asyncio.create_task(self._periodic_save())
        self._running_tasks.append(task)

        # 心跳任務
        task = asyncio.create_task(self._heartbeat())
        self._running_tasks.append(task)

    async def _periodic_save(self):
        """定期保存"""
        while self.state.running:
            try:
                await asyncio.sleep(self.config.auto_save_interval)

                if self.memory_manager:
                    await self.memory_manager.flush()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定期保存失敗: {e}")

    async def _heartbeat(self):
        """心跳"""
        while self.state.running:
            try:
                await asyncio.sleep(60)

                # 更新最後活躍時間
                if self.state.session_id and self.memory_manager:
                    await self.memory_manager.update_session(
                        self.state.session_id,
                        {"last_active": datetime.now().isoformat()},
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳失敗: {e}")

    def get_state(self) -> ApplicationState:
        """獲取當前狀態"""
        return self.state


# ============================================================
# 快捷創建函數
# ============================================================


async def create_desktop_integration(
    db_path: str = "data/persistent_memory.db", config: IntegrationConfig = None
) -> DesktopIntegration:
    """
    創建桌面整合器

    Args:
        db_path: 資料庫路徑
        config: 配置

    Returns:
        桌面整合器實例
    """
    if config is None:
        config = IntegrationConfig(db_path=db_path)

    integration = DesktopIntegration(config)
    await integration.initialize()

    return integration


# ============================================================
# 上下文管理器支持
# ============================================================


class DesktopIntegrationContext:
    """桌面整合器上下文管理器"""

    def __init__(self, config: IntegrationConfig = None):
        self.config = config
        self.integration: Optional[DesktopIntegration] = None

    async def __aenter__(self) -> DesktopIntegration:
        self.integration = await create_desktop_integration(config=self.config)
        return self.integration

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.integration:
            await self.integration.shutdown()


# ============================================================
# 使用範例
# ============================================================


async def main():
    """使用範例"""
    # 創建整合器
    integration = await create_desktop_integration()

    try:
        # 創建對話
        session_id = await integration.create_session("測試對話")

        # 發送訊息
        await integration.send_message("你好，AI 助手！")

        # 獲取回應（這裡模擬）
        await integration.receive_response("你好！有什麼可以幫助你的？")

        # 列出所有對話
        sessions = await integration.list_sessions()
        for session in sessions:
            print(f"會話: {session.title} - {session.message_count} 條訊息")

        # 創建任務
        task_id = await integration.create_task(
            title="完成報告", description="撰寫月度報告", priority=5
        )

        # 更新任務進度
        await integration.update_task_progress(task_id, 50, "已完成一半")

        # 建議快速回覆
        suggestions = await integration.suggest_quick_reply("謝謝")
        print(f"建議回覆: {suggestions}")

        # 導出任務
        await integration.export_tasks_csv("tasks_export.csv")

    finally:
        # 關閉
        await integration.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化記憶系統 - 狀態恢復管理器
Persistent Memory System - State Restorer

功能：
- 檢測未完成的對話
- 恢復對話上下文
- 恢復智能體狀態
- 恢復任務進度

作者：AI 智能體
創建時間：2026-03-21
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 資料類別定義
# ============================================================


@dataclass
class SessionSnapshot:
    """會話快照"""

    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    is_active: bool
    context_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RestoreResult:
    """恢復結果"""

    success: bool
    restored_items: List[str] = field(default_factory=list)
    failed_items: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    restored_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStateSnapshot:
    """智能體狀態快照"""

    state_id: str
    agent_id: str
    state_name: str
    created_at: str
    data: Dict[str, Any]
    version: int


@dataclass
class TaskProgress:
    """任務進度"""

    task_id: str
    task_name: str
    status: str  # 'pending', 'in_progress', 'completed', 'failed'
    progress: float  # 0-100
    created_at: str
    updated_at: str
    due_date: Optional[str] = None


# ============================================================
# 狀態恢復管理器
# ============================================================


class StateRestorer:
    """
    狀態恢復管理器

    功能：
    - 檢測未完成的對話會話
    - 恢復對話上下文
    - 恢復智能體狀態
    - 恢復任務進度
    - 支援時間範圍過濾
    - 自動備份

    使用範例：
        restorer = StateRestorer(storage_manager)

        # 恢復所有未完成的會話
        result = restorer.restore_all_unfinished()

        # 恢復指定會話
        session = restorer.restore_session("session_123")

        # 恢復智能體狀態
        agent_state = restorer.restore_agent_state("agent_456")

        # 恢復任務進度
        tasks = restorer.restore_tasks(status_filter="in_progress")
    """

    def __init__(
        self, storage_manager, max_inactive_hours: int = 24, auto_cleanup_days: int = 30
    ):
        """
        初始化狀態恢復管理器

        Args:
            storage_manager: 儲存管理器實例
            max_inactive_hours: 最大非活躍小時數（超過視為未完成）
            auto_cleanup_days: 自動清理天數（超過此時間的舊資料）
        """
        self.storage = storage_manager
        self.max_inactive_hours = max_inactive_hours
        self.auto_cleanup_days = auto_cleanup_days

        # 緩存最近恢復的資料
        self._cache: Dict[str, Any] = {}
        self._cache_enabled = True
        self._cache_ttl = 300  # 5分鐘

    def is_session_unfinished(self, session_id: str) -> bool:
        """
        檢查會話是否未完成

        Args:
            session_id: 會話 ID

        Returns:
            是否未完成
        """
        sessions = self.storage.read("sessions", conditions={"session_id": session_id})

        if not sessions:
            return False

        session = sessions[0]

        # 檢查是否標記為活動
        if session.get("is_active", 0) == 1:
            return True

        # 檢查最後活動時間
        updated_at = session.get("updated_at")
        if updated_at:
            try:
                last_update = datetime.fromisoformat(updated_at)
                hours_inactive = (datetime.now() - last_update).total_seconds() / 3600
                return hours_inactive < self.max_inactive_hours
            except Exception:
                return False

        return False

    def get_unfinished_sessions(self) -> List[SessionSnapshot]:
        """
        取得所有未完成的會話

        Returns:
            未完成會話列表
        """
        sessions = self.storage.read("sessions", order_by="updated_at DESC")

        unfinished = []
        for session in sessions:
            # 檢查是否活動
            if session.get("is_active", 0) == 1:
                unfinished.append(
                    SessionSnapshot(
                        session_id=session["session_id"],
                        title=session.get("title", "未命名"),
                        created_at=session.get("created_at", ""),
                        updated_at=session.get("updated_at", ""),
                        message_count=session.get("message_count", 0),
                        is_active=True,
                        context_data=json.loads(session.get("context_data", "{}")),
                    )
                )
                continue

            # 檢查時間
            updated_at = session.get("updated_at")
            if updated_at:
                try:
                    last_update = datetime.fromisoformat(updated_at)
                    hours_inactive = (
                        datetime.now() - last_update
                    ).total_seconds() / 3600
                    if hours_inactive < self.max_inactive_hours:
                        unfinished.append(
                            SessionSnapshot(
                                session_id=session["session_id"],
                                title=session.get("title", "未命名"),
                                created_at=session.get("created_at", ""),
                                updated_at=updated_at,
                                message_count=session.get("message_count", 0),
                                is_active=False,
                                context_data=json.loads(
                                    session.get("context_data", "{}")
                                ),
                            )
                        )
                except Exception:
                    pass

        return unfinished

    def restore_session(
        self, session_id: str, include_messages: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        恢復指定會話

        Args:
            session_id: 會話 ID
            include_messages: 是否包含訊息

        Returns:
            會話資料，若不存在則返回 None
        """
        # 檢查快取
        cache_key = f"session_{session_id}"
        if self._cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - cached.get("_cached_at", 0) < self._cache_ttl:
                return cached.get("data")

        # 取得會話
        sessions = self.storage.read("sessions", conditions={"session_id": session_id})

        if not sessions:
            logger.warning(f"找不到會話: {session_id}")
            return None

        session = sessions[0]

        # 構建恢復資料
        restored = {
            "session_id": session["session_id"],
            "title": session.get("title", "未命名"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "message_count": session.get("message_count", 0),
            "is_active": session.get("is_active", 0) == 1,
            "context_data": json.loads(session.get("context_data", "{}")),
            "_restored_at": datetime.now().isoformat(),
        }

        # 取得訊息
        if include_messages:
            messages = self.storage.read(
                "messages",
                conditions={"session_id": session_id},
                order_by="created_at ASC",
            )
            restored["messages"] = [
                {
                    "message_id": m["message_id"],
                    "role": m.get("role", ""),
                    "content": m.get("content", ""),
                    "created_at": m.get("created_at"),
                }
                for m in messages
            ]

        # 快取結果
        if self._cache_enabled:
            restored["_cached_at"] = time.time()
            self._cache[cache_key] = restored

        return restored

    def restore_all_unfinished(self) -> RestoreResult:
        """
        恢復所有未完成的會話

        Returns:
            恢復結果
        """
        result = RestoreResult(success=True)

        # 取得所有未完成的會話
        unfinished = self.get_unfinished_sessions()

        if not unfinished:
            result.warnings.append("沒有找到未完成的會話")
            return result

        # 恢復每個會話
        restored_sessions = []
        for session in unfinished:
            restored = self.restore_session(session.session_id)
            if restored:
                restored_sessions.append(restored)
                result.restored_items.append(f"session:{session.session_id}")
            else:
                result.failed_items.append(f"session:{session.session_id}")

        result.restored_data["sessions"] = restored_sessions
        result.restored_data["count"] = len(restored_sessions)

        logger.info(f"恢復了 {len(restored_sessions)} 個未完成的會話")

        return result

    def get_agent_states(self, agent_id: str) -> List[AgentStateSnapshot]:
        """
        取得智能體狀態列表

        Args:
            agent_id: 智能體 ID

        Returns:
            智能體狀態列表
        """
        states = self.storage.read(
            "agent_states",
            conditions={"agent_id": agent_id},
            order_by="created_at DESC",
        )

        return [
            AgentStateSnapshot(
                state_id=s["state_id"],
                agent_id=s["agent_id"],
                state_name=s.get("state_name", ""),
                created_at=s.get("created_at", ""),
                data=json.loads(s.get("data", "{}")),
                version=s.get("version", 1),
            )
            for s in states
        ]

    def restore_agent_state(
        self, agent_id: str, version: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        恢復智能體狀態

        Args:
            agent_id: 智能體 ID
            version: 指定版本（可選，預設為最新）

        Returns:
            智能體狀態資料
        """
        # 檢查快取
        cache_key = f"agent_{agent_id}_{version or 'latest'}"
        if self._cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        # 查詢條件
        conditions = {"agent_id": agent_id}
        if version is not None:
            conditions["version"] = version

        states = self.storage.read(
            "agent_states", conditions=conditions, order_by="created_at DESC", limit=1
        )

        if not states:
            logger.warning(f"找不到智能體狀態: {agent_id}")
            return None

        state = states[0]

        restored = {
            "state_id": state["state_id"],
            "agent_id": state["agent_id"],
            "state_name": state.get("state_name", ""),
            "created_at": state.get("created_at"),
            "data": json.loads(state.get("data", "{}")),
            "version": state.get("version", 1),
        }

        # 快取
        if self._cache_enabled:
            restored["_cached_at"] = time.time()
            self._cache[cache_key] = restored

        return restored

    def restore_tasks(
        self,
        status_filter: Optional[str] = None,
        date_range: Optional[Tuple[str, str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        恢復任務

        Args:
            status_filter: 狀態過濾（pending, in_progress, completed, failed）
            date_range: 日期範圍 (start_date, end_date)
            limit: 返回數量限制

        Returns:
            任務列表
        """
        # 構建查詢條件
        conditions = {}

        if status_filter:
            conditions["status"] = status_filter

        # 讀取任務
        tasks = self.storage.read(
            "tasks",
            conditions=conditions if conditions else None,
            order_by="updated_at DESC",
            limit=limit,
        )

        # 日期範圍過濾
        if date_range:
            start_date, end_date = date_range
            filtered = []
            for task in tasks:
                task_date = task.get("created_at", "")
                if start_date <= task_date <= end_date:
                    filtered.append(task)
            tasks = filtered

        return [
            {
                "task_id": t["task_id"],
                "task_name": t.get("task_name", ""),
                "status": t.get("status", "pending"),
                "progress": t.get("progress", 0.0),
                "created_at": t.get("created_at"),
                "updated_at": t.get("updated_at"),
                "due_date": t.get("due_date"),
            }
            for t in tasks
        ]

    def export_tasks_csv(
        self,
        output_path: str,
        status_filter: Optional[str] = None,
        date_range: Optional[Tuple[str, str]] = None,
    ) -> str:
        """
        匯出任務為 CSV

        Args:
            output_path: 輸出檔案路徑
            status_filter: 狀態過濾
            date_range: 日期範圍

        Returns:
            輸出檔案路徑
        """
        tasks = self.restore_tasks(status_filter, date_range)

        # CSV 標題
        csv_lines = ["task_id,task_name,status,progress,created_at,updated_at,due_date"]

        # CSV 資料行
        for task in tasks:
            line = [
                task["task_id"],
                f'"{task["task_name"]}"',  # 處理包含逗號的名稱
                task["status"],
                str(task["progress"]),
                task.get("created_at", ""),
                task.get("updated_at", ""),
                task.get("due_date", ""),
            ]
            csv_lines.append(",".join(line))

        # 寫入檔案
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(csv_lines))

        logger.info(f"任務已匯出至: {output_path}")

        return output_path

    def restore_all(self) -> RestoreResult:
        """
        恢復所有資料（會話、智能體、任務）

        Returns:
            恢復結果
        """
        result = RestoreResult(success=True)

        # 恢復會話
        session_result = self.restore_all_unfinished()
        result.restored_items.extend(session_result.restored_items)
        result.failed_items.extend(session_result.failed_items)
        result.warnings.extend(session_result.warnings)

        # 取得智能體 ID 列表
        try:
            agents = self.storage.execute_raw_query(
                "SELECT DISTINCT agent_id FROM agent_states"
            )
            agent_ids = [a["agent_id"] for a in agents]

            for agent_id in agent_ids:
                state = self.restore_agent_state(agent_id)
                if state:
                    result.restored_items.append(f"agent_state:{agent_id}")
                else:
                    result.failed_items.append(f"agent_state:{agent_id}")
        except Exception as e:
            logger.warning(f"恢復智能體狀態時出錯: {e}")

        # 取得進行中的任務
        in_progress_tasks = self.restore_tasks(status_filter="in_progress")
        result.restored_data["in_progress_tasks"] = in_progress_tasks
        result.restored_items.extend(
            [f"task:{t['task_id']}" for t in in_progress_tasks]
        )

        logger.info(f"恢復完成: {len(result.restored_items)} 個項目")

        return result

    def clear_cache(self):
        """清除快取"""
        self._cache.clear()
        logger.info("快取已清除")

    def set_cache_ttl(self, ttl_seconds: int):
        """
        設定快取 TTL

        Args:
            ttl_seconds: 快取生存時間（秒）
        """
        self._cache_ttl = ttl_seconds

    def enable_cache(self, enabled: bool):
        """
        啟用/停用快取

        Args:
            enabled: 是否啟用
        """
        self._cache_enabled = enabled
        if not enabled:
            self.clear_cache()

    def get_inactive_sessions(
        self, hours_threshold: Optional[int] = None
    ) -> List[SessionSnapshot]:
        """
        取得非活躍會話

        Args:
            hours_threshold: 小時閾值（可覆蓋預設值）

        Returns:
            非活躍會話列表
        """
        threshold = hours_threshold or self.max_inactive_hours
        sessions = self.storage.read("sessions", order_by="updated_at DESC")

        inactive = []
        for session in sessions:
            updated_at = session.get("updated_at")
            if updated_at:
                try:
                    last_update = datetime.fromisoformat(updated_at)
                    hours_inactive = (
                        datetime.now() - last_update
                    ).total_seconds() / 3600
                    if hours_inactive >= threshold:
                        inactive.append(
                            SessionSnapshot(
                                session_id=session["session_id"],
                                title=session.get("title", "未命名"),
                                created_at=session.get("created_at", ""),
                                updated_at=updated_at,
                                message_count=session.get("message_count", 0),
                                is_active=session.get("is_active", 0) == 1,
                                context_data=json.loads(
                                    session.get("context_data", "{}")
                                ),
                            )
                        )
                except Exception:
                    pass

        return inactive

    def archive_old_sessions(self) -> int:
        """
        歸檔舊會話

        Returns:
            歸檔的會話數量
        """
        days = self.auto_cleanup_days
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        old_sessions = self.storage.read("sessions", conditions={"is_active": 0})

        archived = 0
        for session in old_sessions:
            updated_at = session.get("updated_at", "")
            if updated_at and updated_at < cutoff_date:
                # 標記為歸檔
                self.storage.write(
                    "sessions",
                    {
                        "session_id": session["session_id"],
                        "is_active": -1,  # -1 表示已歸檔
                        "archived_at": datetime.now().isoformat(),
                    },
                    operation_type="update",
                )
                archived += 1

        logger.info(f"歸檔了 {archived} 個舊會話")
        return archived


# ============================================================
# 使用範例
# ============================================================


async def main():
    """使用範例"""
    from storage_manager import create_storage_manager

    # 建立儲存管理器
    storage = await create_storage_manager()

    # 建立狀態恢復管理器
    restorer = StateRestorer(storage)

    # 測試：恢復所有未完成的會話
    print("=== 恢復所有未完成的會話 ===")
    result = restorer.restore_all_unfinished()
    print(f"成功: {result.success}")
    print(f"恢復項目: {result.restored_items}")
    print(f"失敗項目: {result.failed_items}")

    # 測試：取得未完成會話
    print("\n=== 未完成會話列表 ===")
    unfinished = restorer.get_unfinished_sessions()
    for s in unfinished:
        print(f"  - {s.session_id}: {s.title} ({s.message_count} 則訊息)")

    # 測試：恢復任務
    print("\n=== 恢復進行中的任務 ===")
    tasks = restorer.restore_tasks(status_filter="in_progress")
    for t in tasks:
        print(f"  - {t['task_name']}: {t['progress']}%")

    # 測試：取得統計
    print("\n=== 統計資訊 ===")
    print(f"未完成會話數: {len(unfinished)}")
    print(f"進行中任務數: {len(tasks)}")

    # 關閉
    await storage.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

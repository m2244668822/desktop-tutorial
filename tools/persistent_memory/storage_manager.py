#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化記憶系統 - 儲存管理器
Persistent Memory System - Storage Manager

功能：
- 非同步寫入緩衝區管理
- 自動刷新機制
- 錯誤處理和重試邏輯
- 壓縮和批次處理

作者：AI 智能體
創建時間：2026-03-21
"""

import sqlite3
import asyncio
import logging
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from queue import Queue, Empty
from threading import Thread, Lock, Event
from functools import wraps

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 資料類別定義
# ============================================================


@dataclass
class WriteOperation:
    """寫入操作資料類別"""

    operation_id: str
    table_name: str
    data: Dict[str, Any]
    operation_type: str  # 'insert', 'update', 'delete'
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class StorageStats:
    """儲存統計資料類別"""

    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_bytes_written: int = 0
    average_write_time_ms: float = 0.0
    buffer_size: int = 0
    flush_count: int = 0


# ============================================================
# 緩衝區管理類
# ============================================================


class AsyncWriteBuffer:
    """
    非同步寫入緩衝區

    特點：
    - 支援優先順序排序
    - 自動刷新機制（時間/大小閾值）
    - 壓縮多次更新為單一事務
    """

    def __init__(
        self,
        min_flush_size: int = 256 * 1024,  # 256KB
        max_flush_size: int = 1024 * 1024,  # 1MB
        flush_interval: float = 3.0,  # 3秒
        max_buffer_size: int = 1000,
    ):
        """
        初始化緩衝區

        Args:
            min_flush_size: 最小刷新大小（bytes）
            max_flush_size: 最大刷新大小（bytes）
            flush_interval: 自動刷新間隔（秒）
            max_buffer_size: 最大緩衝區大小
        """
        self.min_flush_size = min_flush_size
        self.max_flush_size = max_flush_size
        self.flush_interval = flush_interval
        self.max_buffer_size = max_buffer_size

        self._buffer: List[WriteOperation] = []
        self._buffer_size_bytes: int = 0
        self._lock = Lock()
        self._last_flush_time = time.time()

        # 統計資料
        self.stats = StorageStats()

    def add_operation(self, operation: WriteOperation):
        """新增寫入操作到緩衝區"""
        with self._lock:
            # 檢查緩衝區是否已滿
            if len(self._buffer) >= self.max_buffer_size:
                self._flush(scheduler_triggered=True)

            # 計算資料大小
            data_size = len(json.dumps(operation.data).encode("utf-8"))

            # 優先級插入排序（高優先級在前）
            insert_index = 0
            for i, op in enumerate(self._buffer):
                if operation.priority > op.priority:
                    insert_index = i
                    break
                insert_index = i + 1

            self._buffer.insert(insert_index, operation)
            self._buffer_size_bytes += data_size
            self.stats.buffer_size = len(self._buffer)

            # 檢查是否需要刷新
            self._check_flush_conditions()

    def _check_flush_conditions(self):
        """檢查是否需要刷新"""
        current_time = time.time()
        time_elapsed = current_time - self._last_flush_time

        should_flush = (
            self._buffer_size_bytes >= self.min_flush_size
            or self._buffer_size_bytes >= self.max_flush_size
            or time_elapsed >= self.flush_interval
        )

        if should_flush:
            self._flush(scheduler_triggered=True)

    def _flush(self, scheduler_triggered: bool = False):
        """刷新緩衝區"""
        if not self._buffer:
            return

        # 準備刷新資料
        operations_to_flush = self._buffer.copy()
        estimated_size = self._buffer_size_bytes

        # 清空緩衝區
        self._buffer.clear()
        self._buffer_size_bytes = 0
        self._last_flush_time = time.time()
        self.stats.flush_count += 1
        self.stats.total_operations += len(operations_to_flush)

        return operations_to_flush, estimated_size

    def force_flush(self) -> List[WriteOperation]:
        """強制刷新緩衝區"""
        with self._lock:
            return self._flush(scheduler_triggered=False)[0] if self._buffer else []

    def get_pending_operations(self) -> List[WriteOperation]:
        """取得待處理的寫入操作"""
        with self._lock:
            return self._buffer.copy()

    def get_buffer_size(self) -> int:
        """取得緩衝區大小（bytes）"""
        return self._buffer_size_bytes

    def get_operation_count(self) -> int:
        """取得操作數量"""
        with self._lock:
            return len(self._buffer)


# ============================================================
# 儲存管理器類
# ============================================================


class StorageManager:
    """
    儲存管理器

    功能：
    - 管理 SQLite 資料庫連接
    - 處理非同步寫入操作
    - 自動刷新機制
    - 錯誤處理和重試

    使用範例：
        manager = StorageManager("data/persistent_memory.db")
        await manager.initialize()

        # 非同步寫入
        await manager.async_write(
            "sessions",
            {"session_id": "abc123", "title": "新對話"}
        )

        # 同步寫入（直接寫入）
        manager.write("messages", {...})

        await manager.close()
    """

    def __init__(
        self,
        db_path: str = "data/persistent_memory.db",
        min_flush_size: int = 256 * 1024,
        max_flush_size: int = 1024 * 1024,
        flush_interval: float = 3.0,
        enable_compression: bool = True,
    ):
        """
        初始化儲存管理器

        Args:
            db_path: 資料庫檔案路徑
            min_flush_size: 最小刷新大小（bytes）
            max_flush_size: 最大刷新大小（bytes）
            flush_interval: 自動刷新間隔（秒）
            enable_compression: 啟用資料壓縮
        """
        self.db_path = db_path
        self.enable_compression = enable_compression

        # 資料庫連接
        self.conn: Optional[sqlite3.Connection] = None

        # 緩衝區
        self.buffer = AsyncWriteBuffer(
            min_flush_size=min_flush_size,
            max_flush_size=max_flush_size,
            flush_interval=flush_interval,
        )

        # 後台執行緒
        self._flush_thread: Optional[Thread] = None
        self._running = Event()
        self._lock = Lock()

        # 回調函數
        self._on_flush_callback: Optional[Callable] = None
        self._on_error_callback: Optional[Callable] = None

    async def initialize(self):
        """初始化儲存管理器"""
        self._connect()
        self._start_flush_scheduler()
        logger.info(f"儲存管理器初始化完成: {self.db_path}")

    def _connect(self):
        """連接資料庫"""
        if self.conn is None:
            # 確保目錄存在
            import os

            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            self.conn = sqlite3.connect(
                self.db_path, check_same_thread=False, isolation_level=None
            )
            # 啟用效能優化
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA cache_size=-64000")
            self.conn.execute("PRAGMA temp_store=MEMORY")

    def _start_flush_scheduler(self):
        """啟動刷新排程器"""
        self._running.set()
        self._flush_thread = Thread(target=self._flush_scheduler_loop, daemon=True)
        self._flush_thread.start()

    def _flush_scheduler_loop(self):
        """刷新排程器迴圈"""
        while self._running.is_set():
            try:
                # 檢查是否需要刷新
                pending = self.buffer.get_pending_operations()
                if pending:
                    self._execute_flush(pending)

                # 休眠一段時間
                time.sleep(1)
            except Exception as e:
                logger.error(f"刷新排程器發生錯誤: {e}")
                if self._on_error_callback:
                    self._on_error_callback(e)

    def _execute_flush(self, operations: List[WriteOperation]):
        """執行批量寫入"""
        if not operations or not self.conn:
            return

        start_time = time.time()
        cursor = self.conn.cursor()

        try:
            # 開始事務
            cursor.execute("BEGIN TRANSACTION")

            for op in operations:
                try:
                    self._execute_operation(cursor, op)
                    self.buffer.stats.successful_operations += 1
                except Exception as e:
                    self.buffer.stats.failed_operations += 1
                    logger.error(f"執行操作失敗: {e}")

                    # 重試邏輯
                    if op.retry_count < op.max_retries:
                        op.retry_count += 1
                        self.buffer.add_operation(op)

            # 提交事務
            cursor.execute("COMMIT")

            # 更新統計
            elapsed = (time.time() - start_time) * 1000
            self.buffer.stats.average_write_time_ms = (
                self.buffer.stats.average_write_time_ms
                * (self.buffer.stats.successful_operations - len(operations))
                + elapsed * len(operations)
            ) / max(self.buffer.stats.successful_operations, 1)

        except Exception as e:
            cursor.execute("ROLLBACK")
            logger.error(f"批量寫入失敗: {e}")
            raise

    def _execute_operation(self, cursor: sqlite3.Cursor, operation: WriteOperation):
        """執行單一寫入操作"""
        table_name = operation.table_name
        data = operation.data

        if operation.operation_type == "insert":
            columns = ", ".join(data.keys())
            placeholders = ", ".join(["?" for _ in data])
            values = tuple(data.values())
            cursor.execute(
                f"INSERT OR REPLACE INTO {table_name} ({columns}) VALUES ({placeholders})",
                values,
            )
        elif operation.operation_type == "update":
            set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
            values = tuple(data.values())
            if "id" in data:
                cursor.execute(
                    f"UPDATE {table_name} SET {set_clause} WHERE id = ?",
                    values + (data["id"],),
                )
        elif operation.operation_type == "delete":
            if "id" in data:
                cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (data["id"],))

    async def async_write(
        self,
        table_name: str,
        data: Dict[str, Any],
        priority: int = 0,
        operation_type: str = "insert",
    ):
        """
        非同步寫入資料

        Args:
            table_name: 資料表名稱
            data: 寫入的資料
            priority: 優先級（0-10）
            operation_type: 操作類型 ('insert', 'update', 'delete')
        """
        # 生成唯一操作 ID
        operation_id = hashlib.md5(
            f"{table_name}{time.time()}{json.dumps(data)}".encode()
        ).hexdigest()

        operation = WriteOperation(
            operation_id=operation_id,
            table_name=table_name,
            data=data,
            operation_type=operation_type,
            priority=priority,
        )

        self.buffer.add_operation(operation)

    def write(
        self, table_name: str, data: Dict[str, Any], operation_type: str = "insert"
    ):
        """
        同步寫入資料（直接寫入資料庫）

        Args:
            table_name: 資料表名稱
            data: 寫入的資料
            operation_type: 操作類型
        """
        if not self.conn:
            self._connect()

        cursor = self.conn.cursor()

        try:
            cursor.execute("BEGIN IMMEDIATE")
            op = WriteOperation(
                operation_id="sync_" + str(time.time()),
                table_name=table_name,
                data=data,
                operation_type=operation_type,
            )
            self._execute_operation(cursor, op)
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            raise e

    def read(
        self,
        table_name: str,
        conditions: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        讀取資料

        Args:
            table_name: 資料表名稱
            conditions: 篩選條件
            order_by: 排序欄位
            limit: 結果數量限制
            offset: 偏移量

        Returns:
            資料列表
        """
        if not self.conn:
            self._connect()

        cursor = self.conn.cursor()

        # 建構查詢
        query = f"SELECT * FROM {table_name}"
        params = []

        if conditions:
            where_clauses = [f"{k} = ?" for k in conditions.keys()]
            query += " WHERE " + " AND ".join(where_clauses)
            params = list(conditions.values())

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        query += f" OFFSET {offset}"

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]

        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute_raw_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """執行原始 SQL 查詢"""
        if not self.conn:
            self._connect()

        cursor = self.conn.cursor()
        cursor.execute(query, params)

        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        return []

    def set_flush_callback(self, callback: Callable):
        """設定刷新回調函數"""
        self._on_flush_callback = callback

    def set_error_callback(self, callback: Callable):
        """設定錯誤回調函數"""
        self._on_error_callback = callback

    async def close(self):
        """關閉儲存管理器"""
        # 停止排程器
        self._running.clear()

        # 刷新剩餘緩衝區
        remaining = self.buffer.force_flush()
        if remaining:
            self._execute_flush(remaining)

        # 關閉連接
        if self.conn:
            self.conn.close()
            self.conn = None

        logger.info("儲存管理器已關閉")

    def get_stats(self) -> StorageStats:
        """取得儲存統計"""
        return StorageStats(
            total_operations=self.buffer.stats.total_operations,
            successful_operations=self.buffer.stats.successful_operations,
            failed_operations=self.buffer.stats.failed_operations,
            total_bytes_written=self.buffer.stats.total_bytes_written,
            average_write_time_ms=self.buffer.stats.average_write_time_ms,
            buffer_size=self.buffer.stats.buffer_size,
            flush_count=self.buffer.stats.flush_count,
        )

    def vacuum(self):
        """優化資料庫"""
        if self.conn:
            self.conn.execute("VACUUM")
            logger.info("資料庫已優化")

    def get_size(self) -> int:
        """取得資料庫大小"""
        import os

        if os.path.exists(self.db_path):
            return os.path.getsize(self.db_path)
        return 0


# ============================================================
# 便捷函數
# ============================================================


async def create_storage_manager(
    db_path: str = "data/persistent_memory.db",
) -> StorageManager:
    """
    建立並初始化儲存管理器的便捷函數

    Args:
        db_path: 資料庫檔案路徑

    Returns:
        初始化的 StorageManager 實例
    """
    manager = StorageManager(db_path)
    await manager.initialize()
    return manager


# ============================================================
# 使用範例
# ============================================================


async def main():
    """使用範例"""
    # 建立儲存管理器
    manager = await create_storage_manager()

    # 非同步寫入會話資料
    await manager.async_write(
        "sessions",
        {"session_id": "test_session_001", "title": "測試對話", "is_active": 1},
        priority=5,
    )

    # 同步寫入訊息
    manager.write(
        "messages",
        {
            "message_id": "msg_001",
            "session_id": "test_session_001",
            "role": "user",
            "content": "你好，這是測試訊息",
        },
    )

    # 讀取資料
    sessions = manager.read(
        "sessions", conditions={"is_active": 1}, order_by="created_at DESC", limit=10
    )
    print(f"找到 {len(sessions)} 個活動會話")

    # 取得統計
    stats = manager.get_stats()
    print(f"總操作數: {stats.total_operations}")
    print(f"成功操作數: {stats.successful_operations}")
    print(f"失敗操作數: {stats.failed_operations}")
    print(f"緩衝區大小: {stats.buffer_size}")
    print(f"刷新次數: {stats.flush_count}")

    # 關閉
    await manager.close()


if __name__ == "__main__":
    asyncio.run(main())

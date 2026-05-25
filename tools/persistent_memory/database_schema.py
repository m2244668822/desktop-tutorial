#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化記憶系統 - SQLite 資料庫架構設計
Persistent Memory System - SQLite Database Schema Design

功能：
- 建立資料庫連接
- 創建所需的資料表
- 資料庫遷移管理
- 索引優化

作者：AI 智能體
創建時間：2026-03-21
"""

import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseSchema:
    """
    SQLite 資料庫架構管理類

    負責：
    - 初始化資料庫連接
    - 創建所有必要的資料表
    - 管理資料庫版本和遷移
    - 優化索引以提升查詢效能
    """

    # 資料庫版本
    SCHEMA_VERSION = 1

    # 資料表名稱常量
    TABLE_SESSIONS = "sessions"
    TABLE_MESSAGES = "messages"
    TABLE_AGENT_STATES = "agent_states"
    TABLE_TASKS = "tasks"
    TABLE_QUICK_REPLIES = "quick_replies"
    TABLE_SETTINGS = "settings"
    TABLE_ENCRYPTION_KEYS = "encryption_keys"

    def __init__(self, db_path: str = "data/persistent_memory.db"):
        """
        初始化資料庫架構管理器

        Args:
            db_path: 資料庫檔案路徑（相對於專案根目錄）
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._ensure_database_directory()

    def _ensure_database_directory(self):
        """確保資料庫目錄存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """建立資料庫連接"""
        if self.conn is None:
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None,  # 啟用自動事務
            )
            # 啟用 WAL 模式以提升並發效能
            self.conn.execute("PRAGMA journal_mode=WAL")
            # 啟用外鍵約束
            self.conn.execute("PRAGMA foreign_keys=ON")
            # 設定同步模式為 NORMAL（在效能和安全性之間取得平衡）
            self.conn.execute("PRAGMA synchronous=NORMAL")
            # 快取大小設定（負值表示 KB，正值表示頁數）
            self.conn.execute("PRAGMA cache_size=-64000")  # 64MB
        return self.conn

    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def create_tables(self):
        """
        建立所有必要的資料表

        資料表設計：
        1. sessions - 對話會話表
        2. messages - 訊息表
        3. agent_states - 智能體狀態表
        4. tasks - 任務表
        5. quick_replies - 快速回覆表
        6. settings - 設定表
        7. encryption_keys - 加密金鑰表
        """
        conn = self.connect()
        cursor = conn.cursor()

        try:
            # ============================================================
            # 1. 對話會話表 (sessions)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_message_at TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    is_encrypted INTEGER DEFAULT 0,
                    context_data TEXT,
                    metadata TEXT,
                    INDEX idx_session_id (session_id),
                    INDEX idx_created_at (created_at),
                    INDEX idx_updated_at (updated_at),
                    INDEX idx_is_active (is_active)
                )
            """)

            # ============================================================
            # 2. 訊息表 (messages)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_MESSAGES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    token_count INTEGER,
                    is_encrypted INTEGER DEFAULT 0,
                    encrypted_content BLOB,
                    attachments TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES {self.TABLE_SESSIONS}(session_id)
                        ON DELETE CASCADE,
                    INDEX idx_message_id (message_id),
                    INDEX idx_session_id (session_id),
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_role (role)
                )
            """)

            # ============================================================
            # 3. 智能體狀態表 (agent_states)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_AGENT_STATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state_id TEXT NOT NULL UNIQUE,
                    agent_name TEXT NOT NULL,
                    state_type TEXT NOT NULL,
                    state_data TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_current INTEGER DEFAULT 1,
                    checksum TEXT,
                    INDEX idx_state_id (state_id),
                    INDEX idx_agent_name (agent_name),
                    INDEX idx_version (version),
                    INDEX idx_is_current (is_current)
                )
            """)

            # ============================================================
            # 4. 任務表 (tasks)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_TASKS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'cancelled')),
                    priority INTEGER DEFAULT 0 CHECK(priority BETWEEN 0 AND 5),
                    progress INTEGER DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    due_date TIMESTAMP,
                    completed_at TIMESTAMP,
                    tags TEXT,
                    metadata TEXT,
                    INDEX idx_task_id (task_id),
                    INDEX idx_status (status),
                    INDEX idx_priority (priority),
                    INDEX idx_created_at (created_at),
                    INDEX idx_due_date (due_date)
                )
            """)

            # ============================================================
            # 5. 快速回覆表 (quick_replies)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_QUICK_REPLIES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reply_id TEXT NOT NULL UNIQUE,
                    trigger_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    category TEXT,
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    INDEX idx_reply_id (reply_id),
                    INDEX idx_trigger_text (trigger_text),
                    INDEX idx_category (category),
                    INDEX idx_usage_count (usage_count)
                )
            """)

            # ============================================================
            # 6. 設定表 (settings)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_SETTINGS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT,
                    value_type TEXT DEFAULT 'string',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT,
                    INDEX idx_key (key)
                )
            """)

            # ============================================================
            # 7. 加密金鑰表 (encryption_keys)
            # ============================================================
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_ENCRYPTION_KEYS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id TEXT NOT NULL UNIQUE,
                    key_name TEXT NOT NULL,
                    encrypted_key BLOB NOT NULL,
                    salt BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    algorithm TEXT DEFAULT 'AES-256-GCM',
                    INDEX idx_key_id (key_id)
                )
            """)

            # ============================================================
            # 8. 系統資訊表 (system_info) - 用於追蹤資料庫版本
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_info (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 初始化版本資訊
            cursor.execute(
                """
                INSERT OR IGNORE INTO system_info (key, value)
                VALUES ('schema_version', ?)
            """,
                (str(self.SCHEMA_VERSION),),
            )

            conn.commit()
            logger.info("所有資料表創建完成")

        except Exception as e:
            conn.rollback()
            logger.error(f"創建資料表時發生錯誤: {e}")
            raise

    def get_schema_version(self) -> int:
        """取得當前資料庫架構版本"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT value FROM system_info WHERE key = 'schema_version'
        """)
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def table_exists(self, table_name: str) -> bool:
        """檢查資料表是否存在"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """,
            (table_name,),
        )
        return cursor.fetchone() is not None

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """取得資料表結構資訊"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        return [
            {
                "cid": col[0],
                "name": col[1],
                "type": col[2],
                "notnull": col[3],
                "default_value": col[4],
                "pk": col[5],
            }
            for col in columns
        ]

    def vacuum(self):
        """執行資料庫優化（清理空間）"""
        conn = self.connect()
        conn.execute("VACUUM")
        logger.info("資料庫優化完成")

    def get_database_size(self) -> int:
        """取得資料庫檔案大小（bytes）"""
        if os.path.exists(self.db_path):
            return os.path.getsize(self.db_path)
        return 0

    def backup(self, backup_path: str):
        """備份資料庫"""
        conn = self.connect()
        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        backup_conn.close()
        logger.info(f"資料庫已備份至: {backup_path}")

    def restore(self, backup_path: str):
        """還原資料庫"""
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"備份檔案不存在: {backup_path}")

        # 關閉當前連接
        self.close()

        # 複製備份檔案
        import shutil

        shutil.copy2(backup_path, self.db_path)

        # 重新連接
        self.connect()
        logger.info(f"資料庫已從備份還原: {backup_path}")

    def execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        """執行查詢並返回結果"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    def execute_many(self, query: str, params_list: list):
        """執行批量操作"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.executemany(query, params_list)
        conn.commit()


def create_default_tables(db_path: str = "data/persistent_memory.db") -> DatabaseSchema:
    """
    建立預設資料表的便捷函數

    Args:
        db_path: 資料庫檔案路徑

    Returns:
        DatabaseSchema 實例
    """
    schema = DatabaseSchema(db_path)
    schema.create_tables()
    return schema


# 單元測試
if __name__ == "__main__":
    import tempfile

    # 建立臨時資料庫進行測試
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # 建立資料表
        schema = DatabaseSchema(db_path)
        schema.create_tables()

        # 驗證資料表是否正確創建
        expected_tables = [
            "sessions",
            "messages",
            "agent_states",
            "tasks",
            "quick_replies",
            "settings",
            "encryption_keys",
            "system_info",
        ]

        for table in expected_tables:
            assert schema.table_exists(table), f"資料表 {table} 未正確創建"

        # 驗證版本
        assert schema.get_schema_version() == 1, "版本號不正確"

        # 驗證資料庫大小
        size = schema.get_database_size()
        assert size > 0, "資料庫檔案為空"

        print(f"✓ 所有單元測試通過！")
        print(f"✓ 資料庫大小: {size} bytes")
        print(f"✓ 架構版本: {schema.get_schema_version()}")

    finally:
        schema.close()
        if os.path.exists(db_path):
            os.remove(db_path)

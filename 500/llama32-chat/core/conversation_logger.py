#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
對話記錄器 - 自動記錄與 AI 助手的對話並保存到系統中
用於讓智能體從對話中學習
"""

import os
import json
import sys
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

# 添加父目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils import load_conversations, save_conversations, get_timestamp


class ConversationLogger:
    """對話記錄器類"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.conversations_file = os.path.join(data_dir, "conversations.json")
        self.learning_log_file = os.path.join(data_dir, "learning_log.json")

        # 確保數據目錄存在
        os.makedirs(data_dir, exist_ok=True)

    def log_conversation(
        self,
        user_message: str,
        assistant_response: str,
        context: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        記錄一次對話

        Args:
            user_message: 用戶消息
            assistant_response: AI 助手回應
            context: 上下文信息（如當前文件、任務等）
            tags: 標籤（如 'coding', 'debugging', 'documentation'）

        Returns:
            對話 ID
        """
        conversations = load_conversations()

        # 生成對話 ID
        conv_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 構建對話數據
        conversation = {
            "id": conv_id,
            "timestamp": get_timestamp(),
            "messages": [
                {"role": "user", "content": user_message, "timestamp": get_timestamp()},
                {
                    "role": "assistant",
                    "content": assistant_response,
                    "timestamp": get_timestamp(),
                },
            ],
            "context": context or {},
            "tags": tags or [],
            "source": "conversation_logger",
            "learning_enabled": True,
        }

        # 添加到對話列表
        conversations.append(conversation)

        # 保存
        save_conversations(conversations)

        print(f"✅ 對話已記錄: {conv_id}")
        return conv_id

    def log_programming_session(
        self,
        task_description: str,
        code_changes: List[Dict],
        solutions: List[str],
        learnings: List[str],
    ) -> str:
        """
        記錄一次編程會話

        Args:
            task_description: 任務描述
            code_changes: 代碼變更列表
            solutions: 解決方案列表
            learnings: 學到的知識點

        Returns:
            會話 ID
        """
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 構建會話數據
        session = {
            "id": session_id,
            "timestamp": get_timestamp(),
            "type": "programming_session",
            "task": task_description,
            "code_changes": code_changes,
            "solutions": solutions,
            "learnings": learnings,
            "source": "conversation_logger",
        }

        # 保存到學習日誌
        learning_log = self._load_learning_log()
        learning_log.append(session)
        self._save_learning_log(learning_log)

        # 同時保存為對話格式
        conversation_text = self._format_session_as_conversation(session)
        self.log_conversation(
            user_message=task_description,
            assistant_response=conversation_text,
            tags=["programming", "learning", "code"],
            context={"session_id": session_id},
        )

        print(f"✅ 編程會話已記錄: {session_id}")
        return session_id

    def add_learning_note(
        self, topic: str, content: str, category: Optional[str] = None
    ):
        """
        添加學習筆記

        Args:
            topic: 主題
            content: 內容
            category: 分類（如 'debugging', 'optimization', 'architecture'）
        """
        note = {
            "timestamp": get_timestamp(),
            "topic": topic,
            "content": content,
            "category": category or "general",
        }

        learning_log = self._load_learning_log()
        learning_log.append(note)
        self._save_learning_log(learning_log)

        print(f"✅ 學習筆記已添加: {topic}")

    def export_learning_data(self, output_file: str = "learning_export.json"):
        """
        導出所有學習數據

        Args:
            output_file: 輸出文件名
        """
        # 獲取所有相關數據
        conversations = load_conversations()
        learning_log = self._load_learning_log()

        # 過濾學習相關的對話
        learning_conversations = [
            c
            for c in conversations
            if c.get("learning_enabled") or "learning" in c.get("tags", [])
        ]

        export_data = {
            "export_time": get_timestamp(),
            "total_conversations": len(learning_conversations),
            "total_sessions": len(
                [l for l in learning_log if l.get("type") == "programming_session"]
            ),
            "total_notes": len([l for l in learning_log if "topic" in l]),
            "conversations": learning_conversations,
            "learning_log": learning_log,
        }

        # 保存
        output_path = os.path.join(self.data_dir, output_file)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"✅ 學習數據已導出到: {output_path}")
        print(f"   - 對話: {export_data['total_conversations']} 個")
        print(f"   - 會話: {export_data['total_sessions']} 個")
        print(f"   - 筆記: {export_data['total_notes']} 個")

    def get_learning_summary(self) -> Dict:
        """獲取學習摘要"""
        conversations = load_conversations()
        learning_log = self._load_learning_log()

        learning_conversations = [
            c
            for c in conversations
            if c.get("learning_enabled") or "learning" in c.get("tags", [])
        ]

        # 統計標籤
        all_tags = []
        for conv in learning_conversations:
            all_tags.extend(conv.get("tags", []))

        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "total_conversations": len(learning_conversations),
            "total_sessions": len(
                [l for l in learning_log if l.get("type") == "programming_session"]
            ),
            "total_notes": len([l for l in learning_log if "topic" in l]),
            "popular_tags": sorted(
                tag_counts.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "latest_activity": learning_conversations[-1]["timestamp"]
            if learning_conversations
            else None,
        }

    def _load_learning_log(self) -> List[Dict]:
        """加載學習日誌"""
        if os.path.exists(self.learning_log_file):
            with open(self.learning_log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_learning_log(self, log: List[Dict]):
        """保存學習日誌"""
        with open(self.learning_log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    def _format_session_as_conversation(self, session: Dict) -> str:
        """將編程會話格式化為對話文本"""
        lines = [
            f"## 編程會話記錄",
            f"",
            f"**任務**: {session['task']}",
            f"",
            f"### 代碼變更",
        ]

        for i, change in enumerate(session["code_changes"], 1):
            lines.append(f"{i}. {change.get('description', '未命名變更')}")
            if "file" in change:
                lines.append(f"   文件: {change['file']}")

        lines.extend(
            [
                f"",
                f"### 解決方案",
            ]
        )

        for i, solution in enumerate(session["solutions"], 1):
            lines.append(f"{i}. {solution}")

        lines.extend(
            [
                f"",
                f"### 學習要點",
            ]
        )

        for i, learning in enumerate(session["learnings"], 1):
            lines.append(f"{i}. {learning}")

        return "\n".join(lines)


def quick_log(user_msg: str, assistant_msg: str, tags: List[str] = None):
    """快速記錄對話的便捷函數"""
    logger = ConversationLogger()
    return logger.log_conversation(user_msg, assistant_msg, tags=tags)


if __name__ == "__main__":
    # 示例使用
    logger = ConversationLogger()

    print("=== 對話記錄器測試 ===\n")

    # 記錄一次對話
    logger.log_conversation(
        user_message="如何優化 Python 代碼性能？",
        assistant_response="可以從以下幾個方面優化：1. 使用列表推導式 2. 避免全局變量 3. 使用生成器...",
        tags=["python", "optimization", "performance"],
    )

    # 記錄編程會話
    logger.log_programming_session(
        task_description="修復文檔整合問題",
        code_changes=[
            {"file": "README.md", "description": "更新文檔連結"},
            {"file": "SYSTEM_OVERVIEW.md", "description": "修正架構圖"},
        ],
        solutions=["整合所有文檔到 docs/ 資料夾", "刪除冗餘的 md 文件", "統一命名規範"],
        learnings=[
            "文檔整合需要保持一致的結構",
            "使用編號命名可以改善可讀性",
            "刪除空資料夾要用 find . -type d -empty -delete",
        ],
    )

    # 添加學習筆記
    logger.add_learning_note(
        topic="VS Code 顯示問題",
        content="當資料夾中有空的子資料夾時，VS Code 可能顯示異常。解決方法是刪除空資料夾。",
        category="debugging",
    )

    # 獲取摘要
    summary = logger.get_learning_summary()
    print(f"\n=== 學習摘要 ===")
    print(f"對話數: {summary['total_conversations']}")
    print(f"會話數: {summary['total_sessions']}")
    print(f"筆記數: {summary['total_notes']}")
    print(f"熱門標籤: {summary['popular_tags']}")

    # 導出數據
    logger.export_learning_data()

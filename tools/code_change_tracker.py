#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代碼變更追蹤器 - 自動記錄代碼更新到學習系統
當你修改代碼時，使用這個工具記錄變更
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 將 500/llama32-chat 加入路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

try:
    from conversation_logger import ConversationLogger
    from autonomous_agent import autonomous_agent

    LEARNING_SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  學習系統未完全載入: {e}")
    LEARNING_SYSTEM_AVAILABLE = False


class CodeChangeTracker:
    """代碼變更追蹤器"""

    def __init__(self):
        if LEARNING_SYSTEM_AVAILABLE:
            data_dir = os.path.join(
                os.path.dirname(__file__), "500", "llama32-chat", "data"
            )
            self.logger = ConversationLogger(data_dir=data_dir)
        else:
            self.logger = None

    def log_change(
        self,
        task_description: str,
        files_changed: list,
        change_descriptions: list = None,
        solutions: list = None,
        learnings: list = None,
    ):
        """
        記錄代碼變更

        Args:
            task_description: 任務描述（例如："添加自動啟動 Ollama 功能"）
            files_changed: 修改的文件列表
            change_descriptions: 每個文件的變更描述（可選）
            solutions: 解決方案列表（可選）
            learnings: 學習要點列表（可選）
        """
        if not self.logger:
            print("⚠️  學習系統未啟用，無法記錄變更")
            return

        try:
            # 構建代碼變更列表
            code_changes = []
            for i, file in enumerate(files_changed):
                change = {"file": file}
                if change_descriptions and i < len(change_descriptions):
                    change["description"] = change_descriptions[i]
                else:
                    change["description"] = f"更新 {file}"
                code_changes.append(change)

            # 記錄編程會話
            session_id = self.logger.log_programming_session(
                task_description=task_description,
                code_changes=code_changes,
                solutions=solutions or ["代碼已更新"],
                learnings=learnings or ["完成代碼修改"],
            )

            print(f"\n📝 代碼變更已記錄: {session_id}")

            # 通知智能體更新學習數據
            if LEARNING_SYSTEM_AVAILABLE:
                autonomous_agent.share_learning_insights()
                print("🧠 智能體已更新學習洞察")

            # 顯示記錄摘要
            self._show_summary()

        except Exception as e:
            print(f"❌ 記錄代碼變更時發生錯誤: {e}")

    def _show_summary(self):
        """顯示學習摘要"""
        if not self.logger:
            return

        try:
            summary = self.logger.get_learning_summary()
            print("\n" + "=" * 60)
            print("📊 學習系統摘要")
            print("=" * 60)
            print(f"總對話數: {summary['total_conversations']}")
            print(f"編程會話: {summary['total_sessions']}")
            print(f"學習筆記: {summary['total_notes']}")
            print("=" * 60 + "\n")
        except Exception as e:
            print(f"⚠️  無法顯示摘要: {e}")


def log_current_changes():
    """快速記錄當前的代碼變更"""
    tracker = CodeChangeTracker()

    print("=" * 60)
    print("🔧 代碼變更記錄工具")
    print("=" * 60)

    # 獲取用戶輸入
    print("\n請輸入變更資訊：\n")

    task = input("📋 任務描述: ").strip()
    if not task:
        print("❌ 任務描述不能為空")
        return

    files = input("📁 修改的文件（用逗號分隔）: ").strip()
    if not files:
        print("❌ 至少要指定一個文件")
        return

    files_list = [f.strip() for f in files.split(",")]

    # 可選的詳細資訊
    print("\n以下為可選資訊（直接按 Enter 跳過）：\n")

    solutions_input = input("💡 解決方案（用分號分隔）: ").strip()
    solutions = (
        [s.strip() for s in solutions_input.split(";") if s.strip()]
        if solutions_input
        else None
    )

    learnings_input = input("🎓 學習要點（用分號分隔）: ").strip()
    learnings = (
        [l.strip() for l in learnings_input.split(";") if l.strip()]
        if learnings_input
        else None
    )

    # 記錄變更
    tracker.log_change(
        task_description=task,
        files_changed=files_list,
        solutions=solutions,
        learnings=learnings,
    )

    print("\n✅ 代碼變更記錄完成！")


def quick_log_example():
    """快速記錄範例 - 用於測試"""
    tracker = CodeChangeTracker()

    tracker.log_change(
        task_description="整合智能體學習系統到 chat_client.py",
        files_changed=["chat_client.py", "code_change_tracker.py"],
        change_descriptions=["添加 ConversationLogger 集成", "創建代碼變更追蹤器"],
        solutions=[
            "在每次對話後記錄到學習系統",
            "自動通知智能體更新學習數據",
            "提供程式更新記錄功能",
        ],
        learnings=[
            "ConversationLogger 可以記錄對話和編程會話",
            "autonomous_agent 提供 share_learning_insights() 方法",
            "所有學習數據存儲在 500/llama32-chat/data/ 目錄",
        ],
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="代碼變更追蹤器")
    parser.add_argument("--interactive", "-i", action="store_true", help="互動模式")
    parser.add_argument("--example", "-e", action="store_true", help="記錄範例變更")

    args = parser.parse_args()

    if args.example:
        quick_log_example()
    elif args.interactive:
        log_current_changes()
    else:
        print("使用說明:")
        print("  python code_change_tracker.py --interactive  # 互動式記錄")
        print("  python code_change_tracker.py --example      # 記錄範例")

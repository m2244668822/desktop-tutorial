#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记录当前对话到学习系统"""

import sys
import os

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500/llama32-chat"))

from conversation_logger import ConversationLogger


def main():
    logger = ConversationLogger(data_dir="500/llama32-chat/data")

    # 记录当前对话
    conv_id = logger.log_conversation(
        user_message="所以這次對話有進入對話並且學習嗎？",
        assistant_response=(
            "檢查發現：學習系統已有6個對話、8個編程會話、4個學習筆記。"
            "但當前在VS Code中的對話沒有自動記錄，因為ConversationLogger只集成在chat_client.py中。"
            "建議：(1)通過chat_client.py對話才會自動記錄 (2)重要對話可手動記錄 (3)考慮將VS Code對話也集成到學習系統"
        ),
        tags=["meta-learning", "system-check", "conversation-logging"],
        context={
            "platform": "vscode-copilot",
            "topic": "檢查對話記錄狀態",
            "date": "2026-02-28",
        },
    )

    print(f"✅ 已將當前對話記錄到學習系統: {conv_id}")

    # 添加学习笔记
    logger.add_learning_note(
        topic="對話記錄機制",
        content=(
            "用戶詢問當前對話是否被記錄，發現VS Code中的Copilot對話不會自動記錄到學習系統。"
            "學習系統只記錄通過chat_client.py的對話。建議考慮多平台對話集成機制，"
            "例如：定期掃描VS Code對話歷史、手動記錄重要對話、或開發VS Code擴展插件。"
        ),
        category="system-improvement",
    )

    print("✅ 已添加學習筆記")

    # 显示更新后的摘要
    summary = logger.get_learning_summary()
    print(f"\n📈 更新後統計:")
    print(f"  總對話數: {summary['total_conversations']}")
    print(f"  編程會話數: {summary['total_sessions']}")
    print(f"  學習筆記數: {summary['total_notes']}")
    print(f"  最新活動: {summary.get('latest_activity', '無')}")


if __name__ == "__main__":
    main()

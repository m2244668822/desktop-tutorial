#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速測試學習系統整合
"""

import sys
import os
from pathlib import Path

# 將 500/llama32-chat 加入路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

try:
    from conversation_logger import ConversationLogger
    from autonomous_agent import autonomous_agent

    print("=" * 60)
    print("🧪 學習系統整合測試")
    print("=" * 60)

    # 初始化
    data_dir = os.path.join(os.path.dirname(__file__), "500", "llama32-chat", "data")
    logger = ConversationLogger(data_dir=data_dir)

    print("\n✅ 學習系統已成功初始化")

    # 測試記錄對話
    print("\n📝 測試 1: 記錄對話")
    conv_id = logger.log_conversation(
        user_message="測試學習系統是否正常工作",
        assistant_response="是的，學習系統已經整合完成！每次對話和程式更新都會被記錄。",
        context={
            "api_used": "ollama",
            "source": "test_learning_integration",
            "test": True,
        },
        tags=["test", "learning", "integration"],
    )
    print(f"   對話ID: {conv_id}")

    # 測試記錄程式更新
    print("\n📝 測試 2: 記錄程式更新")
    session_id = logger.log_programming_session(
        task_description="測試程式更新記錄功能",
        code_changes=[
            {"file": "chat_client.py", "description": "整合 ConversationLogger"},
            {"file": "code_change_tracker.py", "description": "創建代碼追蹤工具"},
        ],
        solutions=["在每次對話完成後自動記錄到學習系統", "提供程式更新記錄工具"],
        learnings=[
            "智能體學習系統可以記錄對話和程式更新",
            "所有記錄數據存儲在 data/ 目錄下",
        ],
    )
    print(f"   會話ID: {session_id}")

    # 測試智能體學習共享
    print("\n📝 測試 3: 智能體學習共享")
    autonomous_agent.share_learning_insights()
    print("   ✅ 智能體已更新學習洞察")

    # 顯示學習摘要
    print("\n📊 學習系統摘要")
    print("=" * 60)
    summary = logger.get_learning_summary()
    print(f"總對話數: {summary['total_conversations']}")
    print(f"編程會話: {summary['total_sessions']}")
    print(f"學習筆記: {summary['total_notes']}")

    if summary["popular_tags"]:
        print(f"\n熱門標籤:")
        for tag, count in summary["popular_tags"][:5]:
            print(f"  • {tag}: {count} 次")

    if summary["latest_activity"]:
        print(f"\n最後活動: {summary['latest_activity']}")

    print("=" * 60)
    print("\n✅ 所有測試通過！學習系統整合成功！")
    print("\n💡 提示:")
    print("  • 每次使用 chat_client.py 對話時，都會自動記錄")
    print("  • 使用 code_change_tracker.py 記錄程式更新")
    print("  • 所有學習數據存儲在 500/llama32-chat/data/")

except Exception as e:
    print(f"❌ 測試失敗: {e}")
    import traceback

    traceback.print_exc()

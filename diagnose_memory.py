#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
診斷本地記憶系統 - 檢查所有記憶源的加載狀態
Diagnose local memory system - Check all memory sources
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "tools"))


def diagnose_memory_sources():
    """診斷所有記憶源"""
    print("\n" + "=" * 80)
    print("  🔍 本地記憶系統診斷")
    print("=" * 80)
    print()

    # 定義所有應該存在的記憶源
    memory_sources = {
        "conversation_logs": BASE_DIR
        / "data/conversation_logs/conversations_20260301.json",
        "chat_memory": BASE_DIR / "config/chat_memory.json",
        "main_conversations": BASE_DIR / "500/llama32-chat/data/conversations.json",
        "optimizations": BASE_DIR / "data/conversation_logs/optimizations.json",
        "bug_tracker": BASE_DIR / "data/conversation_logs/bug_tracker.json",
        "chatgpt_database": BASE_DIR
        / "500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json",
        "knowledge_base": BASE_DIR
        / "500/llama32-chat/data/local_knowledge/local_knowledge_base.json",
        "data_index": BASE_DIR
        / "500/llama32-chat/data/local_knowledge/complete_data_index.json",
        "sessions": BASE_DIR / "500/llama32-chat/sessions",
        "unified_insights": BASE_DIR / "500/llama32-chat/data/unified_insights.json",
        "collaboration_context": BASE_DIR
        / "500/llama32-chat/logs/collaboration_context.json",
        "daily_routine": BASE_DIR / "logs/daily_routine_20260301.json",
        "agent_work_log": BASE_DIR / "logs/agent_work_log.json",
    }

    print("📂 檢查記憶源狀態:\n")

    available = 0
    missing = 0
    total_items = 0

    for name, path in memory_sources.items():
        exists = path.exists()
        status = "✅" if exists else "❌"

        if exists:
            available += 1

            # 簡單統計項目
            try:
                if path.is_file():
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            count = len(data)
                        elif isinstance(data, dict):
                            # 如果有 'messages' 或其他列表字段
                            if "messages" in data:
                                count = len(data["messages"])
                            else:
                                count = len(data)
                        else:
                            count = 1
                    print(
                        f"{status} {name:25} | 項目: {count:5} | {path.relative_to(BASE_DIR)}"
                    )
                    total_items += count
                else:
                    # 目錄
                    item_count = len(list(path.glob("**/*")))
                    print(
                        f"{status} {name:25} | 項目: {item_count:5} | {path.relative_to(BASE_DIR)}"
                    )
                    total_items += item_count
            except Exception as e:
                print(f"{status} {name:25} | ⚠️  解析失敗: {str(e)[:30]}")
        else:
            missing += 1
            print(f"{status} {name:25} | 缺失 | {path.relative_to(BASE_DIR)}")

    print()
    print("=" * 80)
    print(f"  📊 統計摘要")
    print("=" * 80)
    print(f"總記憶源: {len(memory_sources)}")
    print(f"可用: {available} ✅")
    print(f"缺失: {missing} ❌")
    print(f"總記憶項目: {total_items:,}")
    print()

    if missing > 0:
        print("⚠️  缺失的記憶源列表:")
        for name, path in memory_sources.items():
            if not path.exists():
                print(f"   • {name}: {path.relative_to(BASE_DIR)}")
        print()

    return available, missing, total_items


def diagnose_api_loading():
    """診斷 LocalMemoryAPI 的實際加載情況"""
    print("\n" + "=" * 80)
    print("  🔧 LocalMemoryAPI 加載診斷")
    print("=" * 80)
    print()

    try:
        from local_memory_api import LocalMemoryAPI

        print("初始化 LocalMemoryAPI...")
        api = LocalMemoryAPI(str(BASE_DIR))
        print()

        print("嘗試加載所有對話...")
        all_convs = api.get_all_conversations()
        print(f"✅ 成功加載 {len(all_convs)} 條對話")
        print()

        # 顯示前 3 條對話摘要
        if all_convs:
            print("最近的對話摘要:")
            for i, conv in enumerate(all_convs[-3:], 1):
                if isinstance(conv, dict):
                    title = conv.get("title", "未命名")[:40]
                    messages = conv.get("messages", [])
                    print(f"  {i}. {title} ({len(messages)} 條訊息)")

        print()
        return True
    except Exception as e:
        print(f"❌ API 加載失敗: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    print("\n🚀 正在診斷本地記憶系統...\n")

    available, missing, total = diagnose_memory_sources()
    diagnose_api_loading()

    print("\n" + "=" * 80)
    print("  ✅ 診斷完成")
    print("=" * 80)
    print()

    if missing == 0:
        print("🎉 所有記憶源都已找到！")
    else:
        print(f"⚠️  {missing} 個記憶源缺失，但系統可以使用 {available} 個可用的源")

    print(f"總共 {total:,} 條記憶項目已就緒")
    print()


if __name__ == "__main__":
    main()

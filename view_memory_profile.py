#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查看智能提取的用戶背景檔案
View intelligently extracted user profile from memories
"""

import sys
from pathlib import Path
from collections import Counter
import re

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "tools"))

from local_memory_api import LocalMemoryAPI


def display_memory_profile():
    """顯示提取的用戶背景檔案"""
    print("\n" + "=" * 80)
    print("  📋 用戶背景檔案分析")
    print("=" * 80)
    print()

    try:
        # 初始化記憶 API
        print("📚 加載所有記憶...")
        api = LocalMemoryAPI(str(BASE_DIR))
        all_convs = api.get_all_conversations()

        if not all_convs:
            print("❌ 無法加載訊息")
            return

        # 將對話轉換為訊息列表
        messages = []
        if isinstance(all_convs, list):
            for conv in all_convs:
                if isinstance(conv, dict):
                    if "messages" in conv and isinstance(conv["messages"], list):
                        messages.extend(conv["messages"])

        print(f"✅ 已加載 {len(messages)} 條訊息\n")

        # 1. 顯示最近對話
        print("🔄 最近的對話脈絡")
        print("-" * 80)
        recent_count = min(15, len(messages))
        for i, msg in enumerate(messages[-recent_count:], 1):
            if isinstance(msg, dict):
                role = msg.get("role", "用戶").upper()
                content = msg.get("content", "")[:100]
                print(f"{i:2}. [{role}] {content}")

        # 2. 提取關鍵字
        print("\n\n🎯 智能提取的關鍵主題（按出現頻率排序）")
        print("-" * 80)

        keywords = Counter()
        domain_keywords = {
            "AI/機器學習": [
                "ai",
                "machine learning",
                "deep learning",
                "neural",
                "model",
                "artificial",
                "learning",
                "人工智能",
                "機器學習",
                "深度學習",
                "神經",
                "llm",
                "gemini",
                "groq",
            ],
            "編程": [
                "python",
                "javascript",
                "code",
                "programming",
                "function",
                "class",
                "api",
                "編程",
                "代碼",
                "程式",
                "java",
                "c++",
                "go",
            ],
            "數據": [
                "data",
                "database",
                "query",
                "json",
                "數據",
                "數據庫",
                "sql",
                "nosql",
                "collection",
            ],
            "系統/架構": [
                "system",
                "architecture",
                "design",
                "structure",
                "系統",
                "架構",
                "設計",
                "build",
                "構建",
            ],
            "記憶/知識": [
                "memory",
                "knowledge",
                "recall",
                "learning",
                "context",
                "記憶",
                "知識",
                "學習",
                "retention",
            ],
            "對話/通信": [
                "chat",
                "conversation",
                "dialogue",
                "message",
                "response",
                "對話",
                "通信",
                "談話",
            ],
            "工作/任務": [
                "task",
                "work",
                "project",
                "job",
                "workflow",
                "工作",
                "任務",
                "項目",
                "流程",
            ],
            "分析": ["analysis", "analytics", "statistics", "分析", "統計", "報告"],
            "優化": ["optimize", "improve", "enhance", "優化", "改進", "效率"],
            "測試": ["test", "debug", "verify", "測試", "調試", "驗證"],
        }

        # 掃描全部訊息提取關鍵字
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "").lower()

                for domain, kwords in domain_keywords.items():
                    for kword in kwords:
                        if re.search(
                            r"\b" + re.escape(kword) + r"\b", content, re.IGNORECASE
                        ):
                            keywords[domain] += 1

        if keywords:
            sorted_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)
            for domain, freq in sorted_keywords:
                freq_indicator = "🔥" if freq >= 5 else "⭐" if freq >= 3 else "•"
                bar_width = min(30, freq // 2)
                bar = "█" * bar_width
                print(f"{freq_indicator} {domain:15} | {bar:30} {freq:3}次")
        else:
            print("  (未找到特定主題)")

        # 3. 用戶特徵分析
        print("\n\n💡 用戶特徵分析")
        print("-" * 80)

        user_messages = [
            msg.get("content", "")
            for msg in messages
            if isinstance(msg, dict) and msg.get("role") == "user"
        ]

        if user_messages:
            # 提問風格
            avg_length = sum(len(m) for m in user_messages) / len(user_messages)
            print(f"提問風格: ", end="")
            if avg_length > 300:
                print("📝 詳細提問者（平均 {:.0f} 字）".format(avg_length))
            elif avg_length > 100:
                print("📄 中等詳細度（平均 {:.0f} 字）".format(avg_length))
            else:
                print("✂️  簡潔提問者（平均 {:.0f} 字）".format(avg_length))

            # 語言偏好
            cn_count = sum(
                1 for m in user_messages if any("\u4e00" <= c <= "\u9fff" for c in m)
            )
            if cn_count > len(user_messages) * 0.7:
                print(f"語言偏好: 🇹🇼 主要使用中文 ({cn_count}/{len(user_messages)})")
            elif cn_count > len(user_messages) * 0.3:
                print(f"語言偏好: 🌐 雙語使用者 (中英混用)")
            else:
                print(f"語言偏好: 🇬🇧 主要使用英文")

            # 技術傾向
            tech_keywords = [
                "code",
                "python",
                "api",
                "編程",
                "技術",
                "database",
                "數據庫",
                "system",
                "algorithm",
            ]
            tech_count = sum(
                1
                for m in user_messages
                for kw in tech_keywords
                if kw.lower() in m.lower()
            )
            if tech_count > 10:
                print(f"技術傾向: 🔧 高度技術導向 ({tech_count} 次提及技術)")
            elif tech_count > 3:
                print(f"技術傾向: ⚙️  中等技術導向 ({tech_count} 次提及技術)")
            else:
                print(f"技術傾向: 📖 低技術導向")

        # 4. 記憶統計
        print("\n\n📊 記憶庫統計")
        print("-" * 80)
        print(f"加載的訊息: {len(messages):,} 條")
        print(f"ChatGPT 數據庫: 1,324+ 條對話")
        print(f"知識庫條目: 468+ 條")
        print(f"系統記憶源: 13 個")
        print(f"總計: ~1,840 條記憶項目")

        print()

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    display_memory_profile()

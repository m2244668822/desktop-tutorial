#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中樞神經系統 (Central Hub)
統一管理所有 AI 模型和 OpenAI 導入數據
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime
import hashlib


class CentralHub:
    """中樞系統 - 統一管理 OpenAI 數據和 AI 模型"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.conversations = {}
        self.openai_contexts = {}
        self.model_references = defaultdict(list)
        self._load_conversations()

    def _load_conversations(self):
        """載入所有對話數據"""
        conv_file = self.data_dir / "conversations.json"
        if conv_file.exists():
            with open(conv_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for conv in data:
                    conv_id = conv.get("conversation_id")
                    self.conversations[conv_id] = conv
                    if conv.get("source") == "openai_export":
                        self.openai_contexts[conv_id] = conv

        print(
            f"✅ 已加載 {len(self.conversations)} 個對話 ({len(self.openai_contexts)} 個來自 OpenAI)"
        )

    def find_similar_conversations(self, query: str, limit: int = 5) -> List[Dict]:
        """查找相似對話"""
        query_lower = query.lower()
        results = []

        for conv_id, conv in self.conversations.items():
            if not conv:
                continue
            title = (conv.get("title") or "").lower()
            messages = conv.get("messages", [])

            # 搜索標題
            if query_lower in title:
                score = 100
            # 搜索消息內容
            else:
                score = 0
                for msg in messages[:5]:  # 只查前 5 條消息
                    text = msg.get("text", "").lower()
                    if query_lower in text:
                        score = 50
                        break

            if score > 0:
                results.append(
                    {
                        "conversation_id": conv_id,
                        "title": conv.get("title"),
                        "message_count": conv.get("message_count", 0),
                        "score": score,
                        "source": conv.get("source", "system"),
                        "create_time": conv.get("create_time"),
                    }
                )

        # 排序並返回前 N 個
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_context_for_query(self, query: str, model: str = None) -> Dict[str, Any]:
        """獲取查詢的上下文（從 OpenAI 導入數據）"""
        similar = self.find_similar_conversations(query, limit=3)

        context = {
            "query": query,
            "model": model,
            "similar_conversations": similar,
            "reference_messages": [],
            "conversation_patterns": {},
        }

        # 提取參考消息
        for conv_info in similar:
            conv = self.conversations.get(conv_info["conversation_id"])
            if conv:
                messages = conv.get("messages", [])
                # 取前 3 條有實質內容的消息
                ref_msgs = []
                for msg in messages:
                    if msg.get("content_type") == "text" and msg.get("text"):
                        ref_msgs.append(
                            {
                                "role": msg.get("role"),
                                "text": msg.get("text")[:200],  # 截取前 200 字
                                "create_time": msg.get("create_time"),
                            }
                        )
                        if len(ref_msgs) >= 3:
                            break
                context["reference_messages"].extend(ref_msgs)

        # 分析對話模式
        context["conversation_patterns"] = self._analyze_patterns(similar)

        return context

    def _analyze_patterns(self, conversations: List[Dict]) -> Dict[str, Any]:
        """分析對話模式"""
        patterns = {
            "common_roles": defaultdict(int),
            "avg_message_count": 0,
            "time_distribution": {},
        }

        if not conversations:
            return patterns

        total_messages = 0
        for conv_info in conversations:
            conv = self.conversations.get(conv_info["conversation_id"])
            if conv:
                total_messages += conv.get("message_count", 0)
                for msg in conv.get("messages", []):
                    role = msg.get("role", "unknown")
                    patterns["common_roles"][role] += 1

        patterns["avg_message_count"] = (
            total_messages / len(conversations) if conversations else 0
        )

        return {
            "common_roles": dict(patterns["common_roles"]),
            "avg_message_count": patterns["avg_message_count"],
        }

    def get_model_recommendation(self, query: str) -> str:
        """根據查詢推薦最合適的模型"""
        context = self.get_context_for_query(query)
        similar = context["similar_conversations"]

        if not similar:
            return "ollama"  # 默認本地模型

        # 基於相似對話的複雜度選擇模型
        avg_msg_count = context["conversation_patterns"].get("avg_message_count", 5)

        if avg_msg_count < 5:
            return "groq"  # 簡單查詢用快速模型
        elif avg_msg_count < 15:
            return "gemini"  # 中等複雜度用 Gemini
        else:
            return "claude"  # 複雜查詢用 Claude

    def record_model_usage(
        self,
        model: str,
        query: str,
        response: str,
        duration: float,
        success: bool = True,
    ):
        """記錄模型使用情況"""
        usage = {
            "model": model,
            "query": query[:100],
            "response_length": len(response),
            "duration": duration,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }

        # 保存使用記錄
        usage_file = self.data_dir / "model_usage.json"
        usage_list = []

        if usage_file.exists():
            with open(usage_file, "r", encoding="utf-8") as f:
                usage_list = json.load(f)

        usage_list.append(usage)

        # 只保留最近 1000 條記錄
        usage_list = usage_list[-1000:]

        with open(usage_file, "w", encoding="utf-8") as f:
            json.dump(usage_list, f, ensure_ascii=False)

    def get_statistics(self) -> Dict[str, Any]:
        """獲取系統統計信息"""
        openai_convs = list(self.openai_contexts.values())
        system_convs = [
            c
            for cid, c in self.conversations.items()
            if c.get("source") != "openai_export"
        ]

        total_messages = 0
        role_distribution = defaultdict(int)

        for conv in self.conversations.values():
            total_messages += conv.get("message_count", 0)
            for msg in conv.get("messages", []):
                role_distribution[msg.get("role", "unknown")] += 1

        return {
            "total_conversations": len(self.conversations),
            "openai_conversations": len(openai_convs),
            "system_conversations": len(system_convs),
            "total_messages": total_messages,
            "role_distribution": dict(role_distribution),
            "average_messages_per_conversation": total_messages
            / len(self.conversations)
            if self.conversations
            else 0,
        }

    def export_context_template(self, query: str, filename: str = None) -> str:
        """導出查詢上下文模板"""
        context = self.get_context_for_query(query)
        model = self.get_model_recommendation(query)

        template = f"""
# 查詢: {query}

## 推薦模型: {model}

## 相似對話:
"""

        for i, conv in enumerate(context["similar_conversations"], 1):
            template += f"\n### {i}. {conv['title']}\n"
            template += f"- 消息數: {conv['message_count']}\n"
            template += f"- 相關度: {conv['score']}%\n"

        template += "\n## 參考消息:\n"
        for i, msg in enumerate(context["reference_messages"][:5], 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            template += f"\n{i}. [{role_emoji} {msg['role']}]\n"
            template += f"   {msg['text']}\n"

        template += f"\n## 對話模式分析:\n"
        patterns = context["conversation_patterns"]
        template += f"- 常見角色: {patterns.get('common_roles', {})}\n"
        template += f"- 平均消息數: {patterns.get('avg_message_count', 0):.1f}\n"

        if filename:
            output_file = Path(filename)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(template)
            return str(output_file)

        return template


def main():
    """測試中樞系統"""
    print("=" * 70)
    print("🧠 中樞神經系統 (Central Hub)")
    print("=" * 70)

    hub = CentralHub()

    # 打印統計信息
    stats = hub.get_statistics()
    print(f"\n📊 系統統計:")
    print(f"   - 總對話數: {stats['total_conversations']}")
    print(f"   - OpenAI 對話: {stats['openai_conversations']}")
    print(f"   - 系統對話: {stats['system_conversations']}")
    print(f"   - 總消息數: {stats['total_messages']}")
    print(f"   - 平均消息/對話: {stats['average_messages_per_conversation']:.1f}")

    # 測試查詢
    test_queries = ["如何編程", "機器學習", "Python 基礎"]

    print(f"\n🔍 查詢測試:")
    for query in test_queries:
        context = hub.get_context_for_query(query)
        model = hub.get_model_recommendation(query)

        print(f"\n   查詢: '{query}'")
        print(f"   推薦模型: {model}")
        print(f"   相似對話: {len(context['similar_conversations'])} 個")

    print("\n" + "=" * 70)
    print("✅ 中樞系統已準備就緒")
    print("=" * 70)


if __name__ == "__main__":
    main()

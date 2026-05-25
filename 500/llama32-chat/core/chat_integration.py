#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡化的聊天集成模塊
使用中樞系統統一管理 AI 模型和 OpenAI 導入數據
"""

from central_hub import CentralHub
from chat import chat_with_model
from autonomous_agent import autonomous_agent
from typing import Dict, Optional, Tuple
import time


class SimplifiedChat:
    """簡化的聊天接口，基於中樞系統"""

    def __init__(self, data_dir: str = "data"):
        self.hub = CentralHub(data_dir)
        self.agent = autonomous_agent

    def chat(
        self, prompt: str, model: str = None, use_context: bool = True
    ) -> Optional[str]:
        """
        簡化的聊天方法

        Args:
            prompt: 用戶輸入
            model: 指定模型（可選）
            use_context: 是否使用 OpenAI 導入數據作為上下文

        Returns:
            模型回應或 None
        """
        start_time = time.time()

        # 步驟 1: 獲取推薦模型和上下文
        if use_context:
            context = self.hub.get_context_for_query(prompt)
            model = model or context.get("recommended_model", "ollama")
        else:
            model = model or "ollama"

        # 步驟 2: 執行聊天
        try:
            response = chat_with_model(model, prompt)

            # 步驟 3: 記錄使用統計
            duration = time.time() - start_time
            self.hub.record_model_usage(
                model=model,
                query=prompt,
                response=response or "",
                duration=duration,
                success=response is not None,
            )

            return response

        except Exception as e:
            print(f"❌ 聊天錯誤: {e}")
            return None

    def smart_chat(self, prompt: str) -> Optional[str]:
        """智能聊天 - 自動選擇最佳模型"""
        return self.chat(prompt, use_context=True)

    def get_context(self, prompt: str) -> Dict:
        """獲取查詢的完整上下文"""
        return self.hub.get_context_for_query(prompt)

    def get_statistics(self) -> Dict:
        """獲取系統統計信息"""
        return self.hub.get_statistics()

    def export_response_template(self, prompt: str) -> str:
        """導出帶有上下文的回應模板"""
        return self.hub.export_context_template(prompt)


def simple_chat(prompt: str, model: str = None) -> Optional[str]:
    """全局簡化聊天函數"""
    chat = SimplifiedChat()
    return chat.chat(prompt, model)


def simple_smart_chat(prompt: str) -> Optional[str]:
    """全局智能聊天函數"""
    chat = SimplifiedChat()
    return chat.smart_chat(prompt)


# 使用示例
if __name__ == "__main__":
    print("=" * 70)
    print("🧠 簡化聊天集成示例")
    print("=" * 70)

    chat = SimplifiedChat()

    # 測試查詢
    test_queries = ["如何學習 Python?", "解釋機器學習", "什麼是函數編程"]

    print("\n📝 系統統計:")
    stats = chat.get_statistics()
    print(f"  - 總對話: {stats['total_conversations']}")
    print(f"  - OpenAI 對話: {stats['openai_conversations']}")
    print(f"  - 消息總計: {stats['total_messages']}")

    print("\n🔍 查詢示例:")
    for query in test_queries:
        print(f"\n  查詢: '{query}'")
        context = chat.get_context(query)
        print(f"  推薦模型: {context.get('recommended_model', 'ollama')}")
        print(f"  相似對話: {len(context['similar_conversations'])} 個")

    print("\n" + "=" * 70)
    print("✅ 簡化集成準備完畢")
    print("=" * 70)

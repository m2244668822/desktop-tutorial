#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神經驅動的聊天系統 (Neural-Driven Chat)
使用神經網絡中樞進行敏感、多層次的決策
"""

from neural_hub import NeuroHub
from chat import chat_with_model
from typing import Dict, Optional, Any, List
import time


class NeuralChat:
    """神經驅動的聊天系統 - 像人類大腦一樣思考"""

    def __init__(self, data_dir: str = "data"):
        self.neural_hub = NeuroHub(data_dir)
        self.conversation_memory = []

    def chat(self, prompt: str, use_neural_analysis: bool = True) -> Dict[str, Any]:
        """
        神經聊天 - 返回完整的神經分析結果

        返回內容包括:
        - response: 模型回應
        - neural_analysis: 詳細的神經分析
        - confidence: 整體置信度
        - sensitivity: 敏感度指標
        - recommendations: 建議
        """
        start_time = time.time()

        # 步驟 1: 神經分析
        print(f"\n{'=' * 70}")
        print(f"🧠 神經聊天系統啟動")
        print(f"{'=' * 70}")

        neural_result = self.neural_hub.process_query(prompt)

        # 步驟 2: 模型選擇和響應
        model = neural_result["model_recommendation"]
        print(f"\n💬 調用模型: {model}")

        response = chat_with_model(model, prompt)

        # 步驟 3: 記錄到記憶
        self.conversation_memory.append(
            {
                "prompt": prompt,
                "response": response,
                "neural_analysis": neural_result,
                "timestamp": time.time(),
            }
        )

        # 步驟 4: 生成完整結果
        duration = time.time() - start_time

        result = {
            "prompt": prompt,
            "response": response,
            "model": model,
            "duration_ms": round(duration * 1000, 2),
            # 神經分析層
            "neural_analysis": {
                "layer_activations": neural_result["neural_analysis"][
                    "activation_cascade"
                ],
                "semantic_analysis": neural_result["neural_analysis"]["semantic_layer"],
                "emotion_profile": neural_result["neural_analysis"]["emotion_layer"],
            },
            # 敏感度指標
            "sensitivity_metrics": {
                "overall": neural_result["sensitivity_indicators"][
                    "overall_sensitivity"
                ],
                "keyword": neural_result["sensitivity_indicators"][
                    "keyword_sensitivity"
                ],
                "context": neural_result["sensitivity_indicators"][
                    "context_sensitivity"
                ],
                "emotion": neural_result["sensitivity_indicators"][
                    "emotion_sensitivity"
                ],
                "confidence": neural_result["sensitivity_indicators"][
                    "relevance_confidence"
                ],
            },
            # 品質指標
            "quality_metrics": {
                "confidence_score": neural_result["confidence_score"],
                "anomaly_score": neural_result["anomaly_score"],
                "reliability": 1.0 - neural_result["anomaly_score"],
            },
            # 邊界條件
            "boundary_conditions": neural_result["boundary_conditions"],
            # 參考信息
            "references": {
                "similar_conversations": neural_result["similar_conversations"][:3],
                "reference_messages": neural_result["reference_messages"],
            },
        }

        # 打印結果摘要
        self._print_neural_summary(result)

        return result

    def _print_neural_summary(self, result: Dict):
        """打印神經分析摘要"""
        print(f"\n📊 神經分析摘要:")
        print(f"   置信度: {result['quality_metrics']['confidence_score']:.1%}")
        print(f"   可靠性: {result['quality_metrics']['reliability']:.1%}")
        print(f"   整體敏感度: {result['sensitivity_metrics']['overall']:.1%}")

        print(f"\n🎯 神經激活層級:")
        for layer, value in result["neural_analysis"]["layer_activations"].items():
            bar = "█" * int(value * 20) + "░" * (20 - int(value * 20))
            print(f"   {layer:12} [{bar}] {value:.1%}")

        boundary = result["boundary_conditions"]
        print(f"\n⚠️  邊界條件:")
        print(f"   - 高信心: {'✓' if boundary['high_confidence'] else '✗'}")
        print(f"   - 清晰意圖: {'✓' if boundary['clear_intent'] else '✗'}")
        print(f"   - 領域內: {'✓' if boundary['within_domain'] else '✗'}")
        print(f"   - 需要澄清: {'✓' if boundary['requires_clarification'] else '✗'}")

        refs = result["references"]["similar_conversations"]
        if refs:
            print(f"\n📚 相關對話 ({len(refs)} 個):")
            for i, ref in enumerate(refs, 1):
                print(f"   {i}. {ref['title'][:50]} ({ref['message_count']} 條消息)")

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """只進行神經分析，不調用模型"""
        return self.neural_hub.process_query(query)

    def get_conversation_memory(self) -> List[Dict]:
        """獲取對話記憶"""
        return self.conversation_memory[-10:]  # 最近 10 條對話

    def get_memory_summary(self) -> Dict[str, Any]:
        """獲取記憶的神經分析摘要"""
        if not self.conversation_memory:
            return {
                "total_interactions": 0,
                "average_confidence": 0.0,
                "most_common_model": None,
            }

        total = len(self.conversation_memory)
        avg_confidence = (
            sum(
                m["neural_analysis"]["confidence_score"]
                for m in self.conversation_memory
            )
            / total
        )

        model_usage = {}
        for m in self.conversation_memory:
            analysis = m["neural_analysis"]
            model = analysis.get("model_recommendation", "unknown")
            model_usage[model] = model_usage.get(model, 0) + 1

        most_common = (
            max(model_usage.items(), key=lambda x: x[1])[0] if model_usage else None
        )

        return {
            "total_interactions": total,
            "average_confidence": avg_confidence,
            "most_common_model": most_common,
            "model_distribution": model_usage,
            "memory_age_seconds": time.time()
            - self.conversation_memory[0]["timestamp"],
        }


def demo():
    """演示神經驅動聊天"""
    print("\n" + "=" * 70)
    print("🧠 神經驅動聊天系統演示")
    print("=" * 70)

    chat = NeuralChat()

    # 測試查詢
    test_queries = [
        "Python 列表和元組的區別是什麼?",
        "如何實現快速排序算法",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'─' * 70}")
        print(f"查詢 #{i}: {query}")
        print(f"{'─' * 70}")

        result = chat.chat(query)

        if result["response"]:
            print(f"\n✨ 模型回應:")
            print(f"{result['response'][:200]}...")

        print(f"\n⏱️  處理時間: {result['duration_ms']} ms")

    # 記憶摘要
    print(f"\n{'=' * 70}")
    print("🧠 神經記憶摘要")
    print(f"{'=' * 70}")

    memory_summary = chat.get_memory_summary()
    print(f"交互次數: {memory_summary['total_interactions']}")
    print(f"平均置信度: {memory_summary['average_confidence']:.1%}")
    print(f"最常用模型: {memory_summary['most_common_model']}")


if __name__ == "__main__":
    demo()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神經網絡中樞系統 (Neural Central Hub)
模擬人類大腦的多層神經元網絡結構
- 多維度敏感分析
- 動態權重調整
- 反饋循環和自適應學習
- 網狀連接和信號聚合
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime
import math


class AnomalyReporter:
    """異常通報系統 - 即時發現和通報異常情況"""

    def __init__(self, log_file: str = "neural_anomalies.json"):
        self.log_file = Path(log_file)
        self.anomalies = []
        self.alerts = []
        self.thresholds = {
            "critical": 0.85,  # 臨界: 置信度 < 15%
            "warning": 0.65,  # 警告: 置信度 < 35%
            "info": 0.45,  # 通知: 置信度 < 55%
        }

    def report_anomaly(
        self, anomaly_type: str, details: Dict[str, Any], severity: str = "info"
    ) -> Dict:
        """報告異常事件"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "type": anomaly_type,
            "severity": severity,
            "details": details,
        }
        self.anomalies.append(report)
        self._trigger_alert(report)
        self._log_anomaly(report)
        return report

    def _trigger_alert(self, report: Dict):
        """觸發告警"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}

        icon = severity_icon.get(report["severity"], "⚪")
        print(f"\n{icon} [異常通報] {timestamp}")
        print(f"   類型: {report['type']}")
        print(f"   嚴重性: {report['severity']}")
        print(f"   詳情: {report['details']}")

        self.alerts.append(report)

    def _log_anomaly(self, report: Dict):
        """記錄異常到文件"""
        if self.log_file.exists():
            with open(self.log_file, "r") as f:
                data = json.load(f)
        else:
            data = {"anomalies": [], "last_updated": None}

        data["anomalies"].append(report)
        data["last_updated"] = datetime.now().isoformat()

        with open(self.log_file, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def check_threshold(self, query: str, confidence: float) -> Optional[Dict]:
        """檢查和評估閾值"""
        for severity, threshold in self.thresholds.items():
            if confidence < threshold:
                if severity == "critical" and confidence < self.thresholds["critical"]:
                    return self.report_anomaly(
                        "low_confidence_query",
                        {
                            "query": query[:100],
                            "confidence": f"{confidence:.2%}",
                            "threshold": f"{threshold:.2%}",
                        },
                        "critical",
                    )
        return None


class Neuron:
    """神經元 - 表示單個感知點"""

    def __init__(self, name: str, sensitivity: float = 0.5):
        self.name = name
        self.sensitivity = sensitivity  # 敏感度 (0-1)
        self.activation = 0.0  # 當前激活值
        self.history = []  # 激活歷史
        self.connections = {}  # 連接到其他神經元

    def activate(self, signal: float) -> float:
        """激活神經元 (sigmoid 激活函數)"""
        # 應用敏感度
        adjusted_signal = signal * self.sensitivity
        # sigmoid 激活函數
        self.activation = 1.0 / (1.0 + math.exp(-adjusted_signal))
        self.history.append(self.activation)
        return self.activation

    def connect_to(self, other_neuron: "Neuron", weight: float = 0.5):
        """連接到另一個神經元"""
        self.connections[other_neuron.name] = {"neuron": other_neuron, "weight": weight}

    def propagate(self) -> float:
        """向連接的神經元傳播信號"""
        total_propagation = 0.0
        for connection in self.connections.values():
            signal = self.activation * connection["weight"]
            total_propagation += connection["neuron"].activate(signal)
        return (
            total_propagation / len(self.connections)
            if self.connections
            else self.activation
        )


class NeuronLayer:
    """神經元層 - 多個神經元的集合"""

    def __init__(self, layer_name: str, neuron_count: int = 5):
        self.layer_name = layer_name
        self.neurons = [
            Neuron(f"{layer_name}_{i}", sensitivity=min(0.95, 0.45 + ((i % 8) * 0.06)))
            for i in range(neuron_count)
        ]

    def activate_all(self, inputs: List[float]) -> List[float]:
        """激活所有神經元"""
        outputs = []
        for i, neuron in enumerate(self.neurons):
            signal = inputs[i] if i < len(inputs) else 0.0
            output = neuron.activate(signal)
            outputs.append(output)
        return outputs

    def get_activation_pattern(self) -> Dict[str, float]:
        """獲取激活模式"""
        return {neuron.name: neuron.activation for neuron in self.neurons}

    def get_average_activation(self) -> float:
        """獲取平均激活值"""
        if not self.neurons:
            return 0.0
        return sum(n.activation for n in self.neurons) / len(self.neurons)


class NeuroHub:
    """神經網絡中樞系統 - 模擬人類大腦的決策系統（自適應成長版本）"""

    def __init__(
        self,
        data_dir: str = "data",
        neuron_scale: float = None,
        connection_boost: float = None,
        adaptive: bool = True,
    ):
        """
        初始化神經中樞

        Args:
            data_dir: 數據目錄
            neuron_scale: 神經元規模倍數（None時自動計算）
            connection_boost: 連接增強倍數（None時自動計算）
            adaptive: 是否啟用自適應成長（默認True）
        """
        self.data_dir = Path(data_dir)
        self.conversations = {}
        self.openai_contexts = {}
        self.adaptive = adaptive

        # 異常報告系統
        self.anomaly_reporter = AnomalyReporter("neural_anomalies.json")

        # 自適應成長系統
        if self.adaptive:
            try:
                from adaptive_neural_growth import AdaptiveNeuralGrowth
            except ImportError:
                # 如果相對導入失敗，嘗試直接導入
                import sys
                import os

                module_dir = os.path.dirname(os.path.abspath(__file__))
                if module_dir not in sys.path:
                    sys.path.insert(0, module_dir)
                from adaptive_neural_growth import AdaptiveNeuralGrowth
            self.growth_manager = AdaptiveNeuralGrowth()
        else:
            self.growth_manager = None

        # 先載入數據以確定規模
        self._load_conversations()

        # 自動計算或使用指定的成長參數
        if self.adaptive and (neuron_scale is None or connection_boost is None):
            total_convs = len(self.conversations) + len(self.openai_contexts)
            neuron_scale, connection_boost, stage = (
                self.growth_manager.calculate_growth_parameters(
                    total_conversations=total_convs, recent_activity_score=1.0
                )
            )
            print(
                f"🌱 自適應成長: 階段【{stage}】| 數據量 {total_convs} | "
                f"神經元×{neuron_scale:.2f} | 連接×{connection_boost:.2f}"
            )

        self.neuron_scale = max(1.0, neuron_scale if neuron_scale else 1.0)
        self.connection_boost = max(1.0, connection_boost if connection_boost else 1.0)

        # 神經元層級結構（自適應規模）
        self.input_layer = NeuronLayer("Input", self._scaled_count(8))
        self.semantic_layer = NeuronLayer("Semantic", self._scaled_count(6))
        self.context_layer = NeuronLayer("Context", self._scaled_count(6))
        self.emotion_layer = NeuronLayer("Emotion", self._scaled_count(5))
        self.pattern_layer = NeuronLayer("Pattern", self._scaled_count(6))
        self.output_layer = NeuronLayer("Output", self._scaled_count(5))

        # 建立神經元網狀連接
        self._build_neural_network()

        # 記錄成長事件
        if self.adaptive and self.growth_manager:
            total_neurons = self._count_total_neurons()
            total_connections = self._count_total_connections()
            self._record_growth_event(total_neurons, total_connections)

        # 反饋機制
        self.feedback_history = []
        self.learning_rate = 0.1  # 學習率

    def _scaled_count(self, base_count: int) -> int:
        """按神經元擴展倍率計算層大小"""
        return max(base_count, int(round(base_count * self.neuron_scale)))

    def _strengthen_weight(self, base_weight: float) -> float:
        """提升連接權重並限制上界"""
        return min(0.95, base_weight * self.connection_boost)

    def _count_total_connections(self) -> int:
        """統計整體神經連接數"""
        layers = [
            self.input_layer,
            self.semantic_layer,
            self.context_layer,
            self.emotion_layer,
            self.pattern_layer,
            self.output_layer,
        ]
        return sum(
            len(neuron.connections) for layer in layers for neuron in layer.neurons
        )

    def _count_total_neurons(self) -> int:
        """統計整體神經元數量"""
        layers = [
            self.input_layer,
            self.semantic_layer,
            self.context_layer,
            self.emotion_layer,
            self.pattern_layer,
            self.output_layer,
        ]
        return sum(len(layer.neurons) for layer in layers)

    def _record_growth_event(self, total_neurons: int, total_connections: int):
        """記錄神經網絡成長事件"""
        if not self.growth_manager:
            return

        total_convs = len(self.conversations) + len(self.openai_contexts)
        _, _, stage = self.growth_manager.calculate_growth_parameters(total_convs)

        # 檢查是否應該記錄（避免重複記錄）
        if self.growth_manager.should_trigger_growth(total_convs):
            self.growth_manager.record_growth(
                total_conversations=total_convs,
                total_neurons=total_neurons,
                total_connections=total_connections,
                neuron_scale=self.neuron_scale,
                connection_boost=self.connection_boost,
                stage_name=stage,
                metadata={
                    "groq_chats": len(self.conversations),
                    "openai_chats": len(self.openai_contexts),
                },
            )

    def _build_neural_network(self):
        """構建神經元間的網狀連接（升級：強化對接與跨層橋接）"""
        # Input → Semantic
        for i, input_neuron in enumerate(self.input_layer.neurons):
            for j, semantic_neuron in enumerate(self.semantic_layer.neurons):
                weight = self._strengthen_weight(0.5 + (0.1 * ((i + j) % 5)) / 5.0)
                input_neuron.connect_to(semantic_neuron, weight)

        # Semantic → Context
        for semantic_neuron in self.semantic_layer.neurons:
            for context_neuron in self.context_layer.neurons:
                semantic_neuron.connect_to(context_neuron, self._strengthen_weight(0.6))

        # Context → Emotion (上下文影響情感)
        for context_neuron in self.context_layer.neurons:
            for emotion_neuron in self.emotion_layer.neurons:
                context_neuron.connect_to(emotion_neuron, self._strengthen_weight(0.7))

        # Emotion → Output (情感對決策直連)
        for emotion_neuron in self.emotion_layer.neurons:
            for output_neuron in self.output_layer.neurons:
                emotion_neuron.connect_to(output_neuron, self._strengthen_weight(0.72))

        # Context → Pattern（上下文驅動模式記憶）
        for context_neuron in self.context_layer.neurons:
            for pattern_neuron in self.pattern_layer.neurons:
                context_neuron.connect_to(pattern_neuron, self._strengthen_weight(0.68))

        # Pattern → Output (歷史模式影響輸出)
        for pattern_neuron in self.pattern_layer.neurons:
            for output_neuron in self.output_layer.neurons:
                pattern_neuron.connect_to(output_neuron, self._strengthen_weight(0.8))

        # Semantic → Emotion（語義直接調制情感）
        for semantic_neuron in self.semantic_layer.neurons:
            for emotion_neuron in self.emotion_layer.neurons:
                semantic_neuron.connect_to(
                    emotion_neuron, self._strengthen_weight(0.55)
                )

        # Input → Context（快速路徑，處理高緊急度查詢）
        for i, input_neuron in enumerate(self.input_layer.neurons):
            if i % 2 != 0:
                continue
            for context_neuron in self.context_layer.neurons:
                input_neuron.connect_to(context_neuron, self._strengthen_weight(0.5))

        # Pattern → Semantic（回饋橋接，提高對接能力）
        for pattern_neuron in self.pattern_layer.neurons:
            for semantic_neuron in self.semantic_layer.neurons:
                pattern_neuron.connect_to(
                    semantic_neuron, self._strengthen_weight(0.45)
                )

    def _load_conversations(self):
        """載入對話數據"""
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
            f"🧠 神經數據已加載: {len(self.conversations)} 個對話 ({len(self.openai_contexts)} 個 OpenAI)"
        )

    def _tokenize_query(self, query: str) -> List[float]:
        """將查詢轉換為神經輸入信號 (8 維)"""
        query_lower = query.lower()
        signals = [0.0] * 8

        # 信號 1: 查詢長度 (歸一化)
        signals[0] = min(len(query) / 100.0, 1.0)

        # 信號 2: 詞彙豐富度
        unique_words = len(set(query_lower.split()))
        signals[1] = min(unique_words / 20.0, 1.0)

        # 信號 3: 問題傾向 (是否包含問號)
        signals[2] = 1.0 if "?" in query else 0.5

        # 信號 4: 技術性 (英文詞彙比例)
        english_ratio = (
            sum(1 for c in query if ord(c) < 128) / len(query) if query else 0
        )
        signals[3] = english_ratio

        # 信號 5: 複雜度 (句子數量)
        num_sentences = len([s for s in query.split("。") if s.strip()])
        signals[4] = min(num_sentences / 5.0, 1.0)

        # 信號 6: 情感傾向 (檢測特定關鍵詞)
        emotion_keywords = {"好": 0.8, "棒": 0.8, "爛": 0.2, "差": 0.2, "中立": 0.5}
        signals[5] = 0.5  # 默認中立
        for keyword, value in emotion_keywords.items():
            if keyword in query_lower:
                signals[5] = value
                break

        # 信號 7: 專業性 (技術詞彙檢測)
        tech_keywords = {
            "python",
            "api",
            "database",
            "算法",
            "架構",
            "ml",
            "ai",
            "代碼",
        }
        tech_count = sum(1 for kw in tech_keywords if kw in query_lower)
        signals[6] = min(tech_count / 3.0, 1.0)

        # 信號 8: 緊急性 (檢測急迫詞彙)
        urgent_keywords = {"急", "快速", "立即", "馬上", "緊急"}
        signals[7] = 0.8 if any(kw in query_lower for kw in urgent_keywords) else 0.3

        return signals

    def _find_relevant_conversations(self, query: str, limit: int = 5) -> List[Dict]:
        """尋找相關對話 (多文本層次分析)"""
        query_lower = query.lower()
        results = []

        for conv_id, conv in self.conversations.items():
            if not conv:
                continue

            title = (conv.get("title") or "").lower()
            messages = conv.get("messages", [])

            # 三層匹配評分
            score = 0.0

            # 層 1: 標題匹配 (精確度高)
            if query_lower in title:
                score += 100 * 0.5  # 權重 50%

            # 層 2: 消息內容匹配 (語義相關)
            content_matches = 0
            for msg in messages:
                text = msg.get("text", "").lower()
                if query_lower in text:
                    content_matches += 1

            if content_matches > 0:
                score += min(content_matches * 20, 50) * 0.3  # 權重 30%

            # 層 3: 對話複雜度相關性
            msg_count = conv.get("message_count", 0)
            query_complexity = len(query.split())

            # 複雜度相近性加分
            if abs(msg_count - query_complexity * 2) < 10:
                score += 20 * 0.2  # 權重 20%

            if score > 0:
                results.append(
                    {
                        "conversation_id": conv_id,
                        "title": conv.get("title"),
                        "message_count": msg_count,
                        "score": score,
                        "source": conv.get("source", "system"),
                        "create_time": conv.get("create_time"),
                        "relevance_depth": content_matches,  # 深度相關性
                    }
                )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def process_query(self, query: str) -> Dict[str, Any]:
        """
        處理查詢 - 通過神經網絡進行多層分析
        返回敏感的、多維度的結果（像人類神經元一樣）
        """
        print(f"\n🧠 神經系統開始處理查詢: '{query}'")

        # 步驟 1: 輸入信號化
        input_signals = self._tokenize_query(query)
        print(f"   📊 輸入信號: {[f'{s:.2f}' for s in input_signals]}")

        # 步驟 2: 輸入層激活
        semantic_inputs = self.input_layer.activate_all(input_signals)
        print(f"   🔴 輸入層激活: {self.input_layer.get_average_activation():.3f}")

        # 步驟 3: 語義層分析
        context_inputs = self.semantic_layer.activate_all(semantic_inputs)
        semantic_analysis = self.semantic_layer.get_activation_pattern()
        print(f"   🟠 語義層激活: {self.semantic_layer.get_average_activation():.3f}")

        # 步驟 4: 上下文層處理
        emotion_inputs = self.context_layer.activate_all(context_inputs)
        context_analysis = self.context_layer.get_activation_pattern()
        print(f"   🟡 上下文層激活: {self.context_layer.get_average_activation():.3f}")

        # 步驟 5: 情感層反應
        output_inputs = self.emotion_layer.activate_all(emotion_inputs)
        emotion_analysis = self.emotion_layer.get_activation_pattern()
        print(f"   🟢 情感層激活: {self.emotion_layer.get_average_activation():.3f}")

        # 步驟 6: 尋找相關對話 (模式識別)
        similar_convs = self._find_relevant_conversations(query, limit=3)

        # 步驟 7: 輸出層決診
        full_decision = self.output_layer.activate_all(output_inputs)

        # 步驟 8: 綜合反饋和敏感度檢測
        result = {
            "query": query,
            "neural_analysis": {
                "input_signals": input_signals,
                "semantic_layer": semantic_analysis,
                "context_layer": context_analysis,
                "emotion_layer": emotion_analysis,
                "activation_cascade": {
                    "input": self.input_layer.get_average_activation(),
                    "semantic": self.semantic_layer.get_average_activation(),
                    "context": self.context_layer.get_average_activation(),
                    "emotion": self.emotion_layer.get_average_activation(),
                    "output": self.output_layer.get_average_activation(),
                },
            },
            "similar_conversations": similar_convs,
            "reference_messages": self._extract_reference_messages(similar_convs),
            "model_recommendation": self._recommend_model_neural(similar_convs),
            "confidence_score": self.output_layer.get_average_activation(),
            "sensitivity_indicators": self._analyze_sensitivity(
                similar_convs, semantic_analysis
            ),
            "boundary_conditions": self._detect_boundary_conditions(
                query, similar_convs
            ),
            "anomaly_score": self._detect_anomaly(query, similar_convs),
        }

        # 步驟 9: 異常檢查和通報
        confidence = result["confidence_score"]
        self.anomaly_reporter.check_threshold(query, confidence)

        # 檢查邊界條件是否有問題
        bc = result["boundary_conditions"]
        if bc["requires_clarification"]:
            self.anomaly_reporter.report_anomaly(
                "requires_clarification",
                {"query": query[:100], "need_more_info": True},
                "warning",
            )

        if not bc["within_domain"]:
            self.anomaly_reporter.report_anomaly(
                "out_of_domain",
                {"query": query[:100], "domain_coverage": "low"},
                "warning",
            )

        return result

    def _extract_reference_messages(self, conversations: List[Dict]) -> List[Dict]:
        """提取參考消息"""
        ref_messages = []
        for conv_info in conversations[:2]:  # 只看前 2 個對話
            conv = self.conversations.get(conv_info["conversation_id"])
            if conv:
                messages = conv.get("messages", [])
                count = 0
                for msg in messages:
                    if (
                        msg.get("content_type") == "text"
                        and msg.get("text")
                        and count < 2
                    ):
                        ref_messages.append(
                            {
                                "role": msg.get("role"),
                                "text": msg.get("text")[:150],
                                "confidence": conv_info["score"] / 100.0,
                            }
                        )
                        count += 1
        return ref_messages

    def _recommend_model_neural(self, conversations: List[Dict]) -> str:
        """基於神經激活的模型推薦"""
        if not conversations:
            return "ollama"

        avg_msg = sum(c["message_count"] for c in conversations) / len(conversations)

        # 複雜度決策
        if avg_msg < 5:
            return "groq"
        elif avg_msg < 15:
            return "gemini"
        else:
            return "claude"

    def _analyze_sensitivity(
        self, conversations: List[Dict], semantic_layer: Dict[str, float]
    ) -> Dict[str, Any]:
        """分析系統的敏感度 (多維度)"""
        return {
            "keyword_sensitivity": max(semantic_layer.values())
            if semantic_layer
            else 0.5,
            "context_sensitivity": self.context_layer.get_average_activation(),
            "emotion_sensitivity": self.emotion_layer.get_average_activation(),
            "relevance_confidence": sum(c["score"] for c in conversations)
            / (len(conversations) * 100)
            if conversations
            else 0.0,
            "overall_sensitivity": (
                max(semantic_layer.values() if semantic_layer else [0.5]) * 0.4
                + self.context_layer.get_average_activation() * 0.3
                + self.emotion_layer.get_average_activation() * 0.3
            ),
        }

    def _detect_boundary_conditions(
        self, query: str, conversations: List[Dict]
    ) -> Dict[str, bool]:
        """偵測邊界條件 (系統能否應對)"""
        return {
            "high_confidence": len(conversations) > 2,
            "clear_intent": self.input_layer.get_average_activation() > 0.6,
            "sufficient_context": len(query) > 10,
            "within_domain": any(c["score"] > 30 for c in conversations)
            if conversations
            else False,
            "requires_clarification": len(conversations) == 0
            or (conversations and conversations[0]["score"] < 30),
        }

    def _detect_anomaly(self, query: str, conversations: List[Dict]) -> float:
        """異常檢測 (查詢是否異常)"""
        if not conversations:
            return 0.8  # 高異常分數

        avg_relevance = sum(c["score"] for c in conversations) / (
            len(conversations) * 100
        )

        # 異常分數計算
        anomaly = 1.0 - avg_relevance

        # 查詢特異性檢測
        if len(query) > 100:
            anomaly *= 1.1  # 非常長的查詢可能異常

        return min(anomaly, 1.0)

    def get_full_status(self) -> Dict[str, Any]:
        """獲取神經系統的完整狀態"""
        status = {
            "system_name": "神經網絡中樞系統 (自適應成長)",
            "topology": {
                "neuron_scale": self.neuron_scale,
                "connection_boost": self.connection_boost,
                "total_neurons": (
                    len(self.input_layer.neurons)
                    + len(self.semantic_layer.neurons)
                    + len(self.context_layer.neurons)
                    + len(self.emotion_layer.neurons)
                    + len(self.pattern_layer.neurons)
                    + len(self.output_layer.neurons)
                ),
                "total_connections": self._count_total_connections(),
            },
            "layers": {
                "input": self.input_layer.get_activation_pattern(),
                "semantic": self.semantic_layer.get_activation_pattern(),
                "context": self.context_layer.get_activation_pattern(),
                "emotion": self.emotion_layer.get_activation_pattern(),
                "pattern": self.pattern_layer.get_activation_pattern(),
                "output": self.output_layer.get_activation_pattern(),
            },
            "data_loaded": {
                "total_conversations": len(self.conversations),
                "openai_conversations": len(self.openai_contexts),
            },
            "learning_rate": self.learning_rate,
            "feedback_history_size": len(self.feedback_history),
        }

        # 添加成長摘要
        if self.growth_manager:
            status["growth_summary"] = self.growth_manager.get_growth_summary()

        return status


def main():
    """測試神經系統"""
    print("=" * 70)
    print("🧠 神經網絡中樞系統 (Neural Central Hub)")
    print("=" * 70)

    hub = NeuroHub()

    # 打印系統狀態
    status = hub.get_full_status()
    print(f"\n✅ 神經系統已初始化")
    print(f"   - 總對話: {status['data_loaded']['total_conversations']}")
    print(f"   - OpenAI 對話: {status['data_loaded']['openai_conversations']}")

    # 測試查詢
    test_queries = ["如何優化 Python 代碼性能?", "機器學習的基本原理", "分布式系統設計"]

    print("\n🔍 神經處理测試:")
    for query in test_queries:
        result = hub.process_query(query)

        print(f"\n📋 查詢結果:")
        print(f"   - 置信度: {result['confidence_score']:.3f}")
        print(
            f"   - 敏感度指標: {result['sensitivity_indicators']['overall_sensitivity']:.3f}"
        )
        print(f"   - 異常分數: {result['anomaly_score']:.3f}")
        print(f"   - 推薦模型: {result['model_recommendation']}")
        print(
            f"   - 邊界條件: 高信心={result['boundary_conditions']['high_confidence']}"
        )

    print("\n" + "=" * 70)
    print("✅ 神經系統準備完畢")
    print("=" * 70)


if __name__ == "__main__":
    main()

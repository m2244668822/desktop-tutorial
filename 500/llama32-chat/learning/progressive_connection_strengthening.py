#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
漸進式連接強化系統
在對話過程中追蹤和強化頻繁使用的神經連接
實現真正的「做中學」機制
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import defaultdict
from datetime import datetime
import math


class ConnectionTracker:
    """神經連接追蹤器 - 記錄連接使用頻率"""

    def __init__(self, log_path: str = "logs/connection_usage.json"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # 連接使用計數 {(neuron_id_1, neuron_id_2): usage_count}
        self.connection_usage = defaultdict(int)

        # 連接權重歷史 {(neuron_id_1, neuron_id_2): [weight_history]}
        self.weight_history = defaultdict(list)

        # 載入歷史記錄
        self._load_history()

    def _load_history(self):
        """載入歷史追蹤數據"""
        if self.log_path.exists():
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 轉換存儲格式
                for key_str, count in data.get("connection_usage", {}).items():
                    # key_str 格式: "neuron_id_1->neuron_id_2"
                    parts = key_str.split("->")
                    if len(parts) == 2:
                        key = (parts[0], parts[1])
                        self.connection_usage[key] = count

                for key_str, history in data.get("weight_history", {}).items():
                    parts = key_str.split("->")
                    if len(parts) == 2:
                        key = (parts[0], parts[1])
                        self.weight_history[key] = history
            except Exception as e:
                print(f"⚠️  載入連接歷史失敗: {e}")

    def _save_history(self):
        """儲存追蹤數據"""
        # 轉換為可序列化格式
        serializable = {
            "connection_usage": {
                f"{k[0]}->{k[1]}": v for k, v in self.connection_usage.items()
            },
            "weight_history": {
                f"{k[0]}->{k[1]}": v for k, v in self.weight_history.items()
            },
            "last_updated": datetime.now().isoformat(),
        }

        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)

    def record_activation(
        self, from_neuron_id: str, to_neuron_id: str, activation_strength: float
    ):
        """記錄一次神經連接激活"""
        key = (from_neuron_id, to_neuron_id)

        # 根據激活強度增加計數（激活強度越高，計數增加越多）
        increment = max(1, int(activation_strength * 10))
        self.connection_usage[key] += increment

    def record_weight_change(
        self, from_neuron_id: str, to_neuron_id: str, new_weight: float
    ):
        """記錄連接權重變化"""
        key = (from_neuron_id, to_neuron_id)

        # 只保留最近50次變化
        history = self.weight_history[key]
        history.append({"timestamp": datetime.now().isoformat(), "weight": new_weight})

        if len(history) > 50:
            self.weight_history[key] = history[-50:]

    def get_usage_score(self, from_neuron_id: str, to_neuron_id: str) -> int:
        """獲取連接使用分數"""
        key = (from_neuron_id, to_neuron_id)
        return self.connection_usage.get(key, 0)

    def get_top_connections(self, limit: int = 20) -> List[Tuple[str, str, int]]:
        """獲取最常用的連接"""
        sorted_connections = sorted(
            self.connection_usage.items(), key=lambda x: x[1], reverse=True
        )

        return [
            (from_id, to_id, count)
            for (from_id, to_id), count in sorted_connections[:limit]
        ]

    def save(self):
        """儲存所有追蹤數據"""
        self._save_history()


class ProgressiveStrengthener:
    """漸進式連接強化器"""

    def __init__(self, tracker: ConnectionTracker = None):
        self.tracker = tracker or ConnectionTracker()

        # 強化策略參數
        self.base_learning_rate = 0.01  # 基礎學習率
        self.max_weight = 0.95  # 最大權重上限
        self.min_weight = 0.1  # 最小權重下限

        # 強化門檻（需要多少次激活才開始強化）
        self.strengthening_threshold = 10

        # 衰減因子（不活躍連接的權重衰減）
        self.decay_rate = 0.001

    def calculate_weight_adjustment(
        self, current_weight: float, usage_count: int, total_sessions: int
    ) -> float:
        """
        計算權重調整量

        Args:
            current_weight: 當前權重
            usage_count: 使用次數
            total_sessions: 總會話數

        Returns:
            新的權重值
        """
        # 計算使用頻率
        usage_frequency = usage_count / max(1, total_sessions)

        # 如果使用頻率高，逐步增強
        if usage_count >= self.strengthening_threshold:
            # 對數增長（避免過快增長）
            growth_factor = math.log(1 + usage_frequency) * self.base_learning_rate
            new_weight = current_weight + growth_factor

            # 限制在範圍內
            new_weight = min(self.max_weight, max(self.min_weight, new_weight))

            return new_weight

        # 如果很少使用，輕微衰減
        elif usage_count < 5 and current_weight > self.min_weight:
            decay = self.decay_rate * (1.0 - usage_frequency)
            new_weight = max(self.min_weight, current_weight - decay)
            return new_weight

        # 保持不變
        return current_weight

    def strengthen_connection(
        self, neuron_from, neuron_to, current_weight: float, total_sessions: int
    ) -> float:
        """
        強化一個神經連接

        Args:
            neuron_from: 源神經元
            neuron_to: 目標神經元
            current_weight: 當前權重
            total_sessions: 總會話數

        Returns:
            調整後的權重
        """
        from_id = f"{neuron_from.layer}_{id(neuron_from)}"
        to_id = f"{neuron_to.layer}_{id(neuron_to)}"

        usage_count = self.tracker.get_usage_score(from_id, to_id)

        new_weight = self.calculate_weight_adjustment(
            current_weight, usage_count, total_sessions
        )

        # 記錄權重變化
        if abs(new_weight - current_weight) > 0.001:  # 只記錄顯著變化
            self.tracker.record_weight_change(from_id, to_id, new_weight)

        return new_weight

    def batch_strengthen(self, neural_hub, total_sessions: int) -> Dict[str, int]:
        """
        批量強化所有連接

        Args:
            neural_hub: 神經中樞實例
            total_sessions: 總會話數

        Returns:
            強化統計 {'strengthened': count, 'decayed': count, 'unchanged': count}
        """
        stats = {"strengthened": 0, "decayed": 0, "unchanged": 0}

        layers = [
            neural_hub.input_layer,
            neural_hub.semantic_layer,
            neural_hub.context_layer,
            neural_hub.emotion_layer,
            neural_hub.pattern_layer,
            neural_hub.output_layer,
        ]

        for layer in layers:
            for neuron in layer.neurons:
                for connected_neuron, current_weight in list(
                    neuron.connections.items()
                ):
                    new_weight = self.strengthen_connection(
                        neuron, connected_neuron, current_weight, total_sessions
                    )

                    # 更新權重
                    neuron.connections[connected_neuron] = new_weight

                    # 統計
                    if new_weight > current_weight + 0.001:
                        stats["strengthened"] += 1
                    elif new_weight < current_weight - 0.001:
                        stats["decayed"] += 1
                    else:
                        stats["unchanged"] += 1

        # 儲存追蹤數據
        self.tracker.save()

        return stats

    def get_strengthening_report(self) -> Dict[str, Any]:
        """獲取強化報告"""
        top_connections = self.tracker.get_top_connections(limit=10)

        return {
            "total_tracked_connections": len(self.tracker.connection_usage),
            "top_10_connections": [
                {"from": from_id, "to": to_id, "usage_count": count}
                for from_id, to_id, count in top_connections
            ],
            "parameters": {
                "base_learning_rate": self.base_learning_rate,
                "strengthening_threshold": self.strengthening_threshold,
                "decay_rate": self.decay_rate,
            },
        }


if __name__ == "__main__":
    print("🔗 漸進式連接強化系統測試\n")

    # 測試追蹤器
    tracker = ConnectionTracker("logs/test_connection_usage.json")

    # 模擬一些激活
    tracker.record_activation("input_1", "semantic_2", 0.8)
    tracker.record_activation("input_1", "semantic_2", 0.9)
    tracker.record_activation("semantic_2", "context_3", 0.7)

    print(
        f"📊 使用分數（input_1 -> semantic_2）: {tracker.get_usage_score('input_1', 'semantic_2')}"
    )

    # 測試強化器
    strengthener = ProgressiveStrengthener(tracker)

    # 模擬權重調整
    test_cases = [
        (0.5, 5, 100),  # 低使用率
        (0.5, 50, 100),  # 高使用率
        (0.8, 100, 100),  # 非常高使用率
    ]

    print("\n🔧 權重調整測試:")
    for current_weight, usage_count, total_sessions in test_cases:
        new_weight = strengthener.calculate_weight_adjustment(
            current_weight, usage_count, total_sessions
        )
        print(
            f"   當前: {current_weight:.3f} | 使用: {usage_count:3d}/{total_sessions:3d} → 新: {new_weight:.3f}"
        )

    print("\n✅ 漸進式連接強化系統就緒")

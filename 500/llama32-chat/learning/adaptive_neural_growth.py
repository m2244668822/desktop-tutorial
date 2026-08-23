#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自適應神經成長系統
根據累積數據和使用情況，逐步調整神經元規模和連接強度
實現「做中學」的漸進式升級機制
"""

import json
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple


class AdaptiveNeuralGrowth:
    """自適應神經成長管理器"""

    def __init__(self, growth_log_path: str = "logs/neural_growth_log.json"):
        self.growth_log_path = Path(growth_log_path)
        self.growth_log_path.parent.mkdir(parents=True, exist_ok=True)

        # 成長歷史記錄
        self.growth_history = self._load_growth_history()

        # 成長階段定義（數據量門檻）
        self.growth_stages = {
            "初生期": {"threshold": 0, "neuron_scale": 1.0, "connection_boost": 1.0},
            "學習期": {"threshold": 500, "neuron_scale": 1.2, "connection_boost": 1.1},
            "成長期": {"threshold": 1000, "neuron_scale": 1.4, "connection_boost": 1.2},
            "發展期": {
                "threshold": 1500,
                "neuron_scale": 1.6,
                "connection_boost": 1.28,
            },
            "成熟期": {
                "threshold": 2000,
                "neuron_scale": 1.8,
                "connection_boost": 1.35,
            },
            "進化期": {"threshold": 3000, "neuron_scale": 2.0, "connection_boost": 1.5},
        }

    def _load_growth_history(self) -> list:
        """載入成長歷史"""
        if self.growth_log_path.exists():
            try:
                with open(self.growth_log_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if not isinstance(raw, list):
                        return []
                    cleaned = []
                    for item in raw:
                        if not isinstance(item, dict):
                            continue
                        topology = item.get("topology") or {}
                        if not isinstance(topology, dict):
                            topology = {}
                        cleaned.append(
                            {
                                "timestamp": item.get("timestamp", datetime.now().isoformat()),
                                "data_volume": int(item.get("data_volume", 0) or 0),
                                "topology": {
                                    "total_neurons": int(topology.get("total_neurons", 0) or 0),
                                    "total_connections": int(
                                        topology.get("total_connections", 0) or 0
                                    ),
                                    "neuron_scale": float(topology.get("neuron_scale", 1.0) or 1.0),
                                    "connection_boost": float(
                                        topology.get("connection_boost", 1.0) or 1.0
                                    ),
                                },
                                "stage": item.get("stage", "初生期"),
                                "metadata": item.get("metadata", {}) or {},
                            }
                        )
                    return cleaned
            except:
                return []
        return []

    def _save_growth_history(self):
        """儲存成長歷史"""
        with open(self.growth_log_path, "w", encoding="utf-8") as f:
            json.dump(self.growth_history, f, ensure_ascii=False, indent=2)

    def calculate_growth_parameters(
        self, total_conversations: int, recent_activity_score: float = 1.0
    ) -> Tuple[float, float, str]:
        """
        根據數據量和活躍度計算成長參數

        Args:
            total_conversations: 總對話數量
            recent_activity_score: 近期活躍度評分 (0.5-1.5)

        Returns:
            (neuron_scale, connection_boost, stage_name)
        """
        # 確定當前成長階段
        current_stage = "初生期"
        neuron_scale = 1.0
        connection_boost = 1.0

        for stage_name, config in sorted(
            self.growth_stages.items(), key=lambda x: x[1]["threshold"], reverse=True
        ):
            if total_conversations >= config["threshold"]:
                current_stage = stage_name
                neuron_scale = config["neuron_scale"]
                connection_boost = config["connection_boost"]
                break

        # 根據活躍度微調（±10%）
        activity_factor = 0.9 + (recent_activity_score - 1.0) * 0.2
        activity_factor = max(0.8, min(1.2, activity_factor))

        neuron_scale *= activity_factor
        connection_boost *= activity_factor

        # 平滑過渡：如果接近下一階段，開始預先成長
        next_threshold = self._get_next_threshold(total_conversations)
        if next_threshold:
            progress = total_conversations / next_threshold
            if progress > 0.8:  # 達到80%時開始過渡
                transition_boost = 1.0 + (progress - 0.8) * 0.5  # 最多+10%
                neuron_scale *= transition_boost
                connection_boost *= transition_boost

        return round(neuron_scale, 3), round(connection_boost, 3), current_stage

    def _get_next_threshold(self, current_count: int) -> int:
        """獲取下一個成長門檻"""
        thresholds = sorted([s["threshold"] for s in self.growth_stages.values()])
        for t in thresholds:
            if t > current_count:
                return t
        return None

    def record_growth(
        self,
        total_conversations: int,
        total_neurons: int,
        total_connections: int,
        neuron_scale: float,
        connection_boost: float,
        stage_name: str,
        metadata: Dict[str, Any] = None,
    ):
        """記錄一次成長事件"""
        growth_record = {
            "timestamp": datetime.now().isoformat(),
            "data_volume": total_conversations,
            "topology": {
                "total_neurons": total_neurons,
                "total_connections": total_connections,
                "neuron_scale": neuron_scale,
                "connection_boost": connection_boost,
            },
            "stage": stage_name,
            "metadata": metadata or {},
        }

        self.growth_history.append(growth_record)
        self._save_growth_history()

        return growth_record

    def get_growth_summary(self) -> Dict[str, Any]:
        """獲取成長摘要"""
        if not self.growth_history:
            return {
                "total_growth_events": 0,
                "current_stage": "未知",
                "growth_trend": "無數據",
            }

        latest = self.growth_history[-1]
        first = self.growth_history[0]

        neuron_growth_rate = (
            (latest["topology"]["total_neurons"] - first["topology"]["total_neurons"])
            / first["topology"]["total_neurons"]
            * 100
            if first["topology"]["total_neurons"] > 0
            else 0
        )

        connection_growth_rate = (
            (
                latest["topology"]["total_connections"]
                - first["topology"]["total_connections"]
            )
            / first["topology"]["total_connections"]
            * 100
            if first["topology"]["total_connections"] > 0
            else 0
        )

        return {
            "total_growth_events": len(self.growth_history),
            "current_stage": latest["stage"],
            "neuron_growth_rate": f"{neuron_growth_rate:.1f}%",
            "connection_growth_rate": f"{connection_growth_rate:.1f}%",
            "data_volume_growth": latest["data_volume"] - first["data_volume"],
            "first_recorded": first["timestamp"],
            "last_updated": latest["timestamp"],
        }

    def should_trigger_growth(self, total_conversations: int) -> bool:
        """判斷是否應該觸發成長"""
        if not self.growth_history:
            return True  # 第一次記錄

        last_record = self.growth_history[-1]
        last_count = int(last_record.get("data_volume", 0) or 0)

        # 每增加100個對話，或跨越成長門檻時觸發
        growth_increment = total_conversations - last_count

        # 檢查是否跨越門檻
        last_stage = last_record.get("stage", "初生期")
        current_stage = self._determine_stage(total_conversations)

        return growth_increment >= 100 or current_stage != last_stage

    def _determine_stage(self, total_conversations: int) -> str:
        """判斷當前應處於哪個階段"""
        for stage_name, config in sorted(
            self.growth_stages.items(), key=lambda x: x[1]["threshold"], reverse=True
        ):
            if total_conversations >= config["threshold"]:
                return stage_name
        return "初生期"


def calculate_activity_score(recent_interactions: int, time_span_days: int) -> float:
    """
    計算最近活躍度評分

    Args:
        recent_interactions: 最近的交互次數
        time_span_days: 時間跨度（天）

    Returns:
        活躍度評分 (0.5-1.5)
    """
    if time_span_days <= 0:
        return 1.0

    # 每天平均交互次數
    avg_per_day = recent_interactions / time_span_days

    # 基準：每天10次交互 = 1.0
    baseline = 10.0
    score = avg_per_day / baseline

    # 限制在 0.5-1.5 範圍
    return max(0.5, min(1.5, score))


if __name__ == "__main__":
    # 測試自適應成長系統
    growth_mgr = AdaptiveNeuralGrowth()

    print("🌱 自適應神經成長系統測試\n")

    # 模擬不同數據量下的成長參數
    test_cases = [100, 500, 1000, 1500, 2000, 2500, 3000, 3500]

    for count in test_cases:
        neuron_scale, connection_boost, stage = growth_mgr.calculate_growth_parameters(
            total_conversations=count, recent_activity_score=1.0
        )
        print(
            f"📊 數據量 {count:4d} | 階段: {stage:6s} | "
            f"神經元倍數: {neuron_scale:.2f} | 連接強度: {connection_boost:.2f}"
        )

    print("\n✅ 自適應成長系統就緒")

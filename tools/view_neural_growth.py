#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神經成長追蹤查看器
顯示系統的自適應成長歷程和統計
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


def load_growth_log(log_path: str = "logs/neural_growth_log.json") -> List[Dict]:
    """載入成長日誌"""
    log_file = Path(log_path)

    if not log_file.exists():
        return []

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 載入成長日誌失敗: {e}")
        return []


def load_connection_usage(log_path: str = "logs/connection_usage.json") -> Dict:
    """載入連接使用記錄"""
    log_file = Path(log_path)

    if not log_file.exists():
        return {}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 載入連接記錄失敗: {e}")
        return {}


def format_timestamp(iso_timestamp: str) -> str:
    """格式化時間戳"""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return iso_timestamp


def display_growth_timeline(growth_log: List[Dict]):
    """顯示成長時間軸"""
    if not growth_log:
        print("📭 尚無成長記錄")
        return

    print("\n" + "=" * 80)
    print("🌱 神經系統成長時間軸")
    print("=" * 80)

    for i, record in enumerate(growth_log, 1):
        timestamp = format_timestamp(record["timestamp"])
        stage = record["stage"]
        data_volume = record["data_volume"]
        topology = record["topology"]

        print(f"\n【記錄 #{i}】 {timestamp}")
        print(f"  階段: {stage}")
        print(f"  數據量: {data_volume} 個對話")
        print(
            f"  拓撲: {topology['total_neurons']} 神經元 | "
            f"{topology['total_connections']} 連接"
        )
        print(
            f"  倍數: 神經元×{topology['neuron_scale']:.2f} | "
            f"連接×{topology['connection_boost']:.2f}"
        )

        if "metadata" in record and record["metadata"]:
            metadata = record["metadata"]
            print(
                f"  元數據: Groq={metadata.get('groq_chats', 0)} | "
                f"OpenAI={metadata.get('openai_chats', 0)}"
            )


def display_growth_stats(growth_log: List[Dict]):
    """顯示成長統計"""
    if not growth_log:
        return

    first = growth_log[0]
    latest = growth_log[-1]

    print("\n" + "=" * 80)
    print("📊 成長統計摘要")
    print("=" * 80)

    # 計算增長率
    neuron_growth = (
        latest["topology"]["total_neurons"] - first["topology"]["total_neurons"]
    )
    neuron_growth_rate = (
        neuron_growth / first["topology"]["total_neurons"] * 100
        if first["topology"]["total_neurons"] > 0
        else 0
    )

    connection_growth = (
        latest["topology"]["total_connections"] - first["topology"]["total_connections"]
    )
    connection_growth_rate = (
        connection_growth / first["topology"]["total_connections"] * 100
        if first["topology"]["total_connections"] > 0
        else 0
    )

    data_growth = latest["data_volume"] - first["data_volume"]

    print(f"\n總記錄次數: {len(growth_log)}")
    print(f"\n初始狀態 ({format_timestamp(first['timestamp'])}):")
    print(f"  - 階段: {first['stage']}")
    print(f"  - 數據: {first['data_volume']} 對話")
    print(f"  - 神經元: {first['topology']['total_neurons']}")
    print(f"  - 連接: {first['topology']['total_connections']}")

    print(f"\n當前狀態 ({format_timestamp(latest['timestamp'])}):")
    print(f"  - 階段: {latest['stage']}")
    print(f"  - 數據: {latest['data_volume']} 對話 (↑{data_growth})")
    print(
        f"  - 神經元: {latest['topology']['total_neurons']} (↑{neuron_growth}, +{neuron_growth_rate:.1f}%)"
    )
    print(
        f"  - 連接: {latest['topology']['total_connections']} (↑{connection_growth}, +{connection_growth_rate:.1f}%)"
    )

    # 階段變化
    stages = [r["stage"] for r in growth_log]
    unique_stages = []
    for s in stages:
        if not unique_stages or s != unique_stages[-1]:
            unique_stages.append(s)

    print(f"\n階段演進: {' → '.join(unique_stages)}")


def display_connection_stats(connection_data: Dict):
    """顯示連接使用統計"""
    if not connection_data:
        print("\n📭 尚無連接使用記錄")
        return

    print("\n" + "=" * 80)
    print("🔗 神經連接使用統計")
    print("=" * 80)

    usage = connection_data.get("connection_usage", {})

    if not usage:
        print("\n尚無連接激活記錄")
        return

    # 排序獲取前10
    sorted_usage = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:10]

    print(f"\n總追蹤連接數: {len(usage)}")
    print(f"最後更新: {connection_data.get('last_updated', '未知')}")

    print("\n🏆 前 10 最活躍連接:")
    for i, (connection, count) in enumerate(sorted_usage, 1):
        print(f"  {i:2d}. {connection:40s} | 激活次數: {count:5d}")

    # 統計總激活
    total_activations = sum(usage.values())
    print(f"\n總激活次數: {total_activations:,}")
    print(f"平均每連接: {total_activations / len(usage):.1f} 次")


def display_growth_graph(growth_log: List[Dict]):
    """顯示簡易成長圖表（ASCII）"""
    if len(growth_log) < 2:
        return

    print("\n" + "=" * 80)
    print("📈 神經元數量成長趨勢")
    print("=" * 80)

    # 提取神經元數量
    neurons = [r["topology"]["total_neurons"] for r in growth_log]

    # 計算縮放比例
    max_neurons = max(neurons)
    min_neurons = min(neurons)
    scale = 50.0 / (max_neurons - min_neurons) if max_neurons > min_neurons else 1.0

    for i, neuron_count in enumerate(neurons):
        # 繪製條形
        bar_length = int((neuron_count - min_neurons) * scale)
        bar = "█" * bar_length

        # 時間戳（簡化）
        timestamp = growth_log[i]["timestamp"][:10]  # 只取日期
        stage = growth_log[i]["stage"][:3]  # 階段簡稱

        print(f"{timestamp} [{stage}] {bar} {neuron_count}")


def main():
    print("=" * 80)
    print("🧠 神經系統自適應成長追蹤器")
    print("=" * 80)

    # 載入數據
    growth_log = load_growth_log()
    connection_data = load_connection_usage()

    if not growth_log and not connection_data:
        print("\n❌ 沒有找到任何成長記錄")
        print("   系統可能尚未開始使用自適應成長功能")
        return

    # 顯示成長時間軸
    display_growth_timeline(growth_log)

    # 顯示成長統計
    display_growth_stats(growth_log)

    # 顯示連接統計
    display_connection_stats(connection_data)

    # 顯示成長圖表
    display_growth_graph(growth_log)

    print("\n" + "=" * 80)
    print("✅ 查看完成")
    print("=" * 80)


if __name__ == "__main__":
    main()

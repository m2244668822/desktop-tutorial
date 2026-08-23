#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神經系統漸進式維護腳本
在使用過程中定期執行，強化活躍連接
"""

import sys
from pathlib import Path

# 添加學習模組路徑
sys.path.insert(0, str(Path(__file__).parent / "500" / "llama32-chat" / "learning"))

from neural_hub import NeuroHub
from progressive_connection_strengthening import (
    ProgressiveStrengthener,
    ConnectionTracker,
)


def perform_progressive_strengthening():
    """執行漸進式連接強化"""
    print("=" * 80)
    print("🔗 神經系統漸進式強化")
    print("=" * 80)

    # 初始化系統
    print("\n🔄 正在載入神經中樞...")
    hub = NeuroHub(data_dir="data", adaptive=True)

    # 獲取當前狀態
    status = hub.get_full_status()
    print(f"\n📊 當前狀態:")
    print(f"   - 系統: {status['system_name']}")
    print(f"   - 神經元: {status['topology']['total_neurons']}")
    print(f"   - 連接: {status['topology']['total_connections']}")
    print(
        f"   - 數據量: {status['data_loaded']['total_conversations']} + "
        f"{status['data_loaded']['openai_conversations']} 對話"
    )

    # 顯示成長摘要
    if (
        "growth_summary" in status
        and status["growth_summary"]["total_growth_events"] > 0
    ):
        summary = status["growth_summary"]
        print(f"\n🌱 成長歷程:")
        print(f"   - 成長事件: {summary['total_growth_events']} 次")
        print(f"   - 當前階段: {summary['current_stage']}")
        print(f"   - 神經元增長: {summary['neuron_growth_rate']}")
        print(f"   - 連接增長: {summary['connection_growth_rate']}")

    # 執行漸進式強化
    print(f"\n🔧 正在執行漸進式連接強化...")

    tracker = ConnectionTracker()
    strengthener = ProgressiveStrengthener(tracker)

    total_sessions = (
        status["data_loaded"]["total_conversations"]
        + status["data_loaded"]["openai_conversations"]
    )

    if total_sessions == 0:
        print("   ⚠️  尚無對話數據，無法進行強化")
        return

    stats = strengthener.batch_strengthen(hub, total_sessions)

    print(f"\n✅ 強化完成:")
    print(f"   - 增強連接: {stats['strengthened']} 個")
    print(f"   - 衰減連接: {stats['decayed']} 個")
    print(f"   - 保持不變: {stats['unchanged']} 個")

    # 獲取強化報告
    report = strengthener.get_strengthening_report()

    if report["total_tracked_connections"] > 0:
        print(f"\n🏆 最活躍連接 (Top 5):")
        for i, conn in enumerate(report["top_10_connections"][:5], 1):
            print(f"   {i}. {conn['from']} → {conn['to']}")
            print(f"      激活次數: {conn['usage_count']}")

    print("\n" + "=" * 80)
    print("💡 提示: 使用 ./view_neural_growth.sh 查看詳細成長歷程")
    print("=" * 80)


def show_growth_status():
    """顯示成長狀態（輕量級）"""
    print("🌱 神經系統成長狀態\n")

    from adaptive_neural_growth import AdaptiveNeuralGrowth

    growth_mgr = AdaptiveNeuralGrowth()
    summary = growth_mgr.get_growth_summary()

    if summary["total_growth_events"] == 0:
        print("   尚未記錄成長事件")
        print("   💡 啟動聊天系統後會自動開始記錄")
        return

    print(f"   總事件: {summary['total_growth_events']}")
    print(f"   當前階段: {summary['current_stage']}")
    print(f"   神經元增長: {summary['neuron_growth_rate']}")
    print(f"   連接增長: {summary['connection_growth_rate']}")
    print(f"   數據增長: {summary['data_volume_growth']} 對話")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="神經系統漸進式維護")
    parser.add_argument(
        "--status-only", action="store_true", help="僅顯示狀態，不執行強化"
    )

    args = parser.parse_args()

    if args.status_only:
        show_growth_status()
    else:
        perform_progressive_strengthening()

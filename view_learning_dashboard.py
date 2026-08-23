#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體學習統計面板
Agent Learning Statistics Dashboard
"""

import json
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent


def display_learning_dashboard():
    """顯示學習統計面板"""
    print("\n" + "=" * 80)
    print("  📊 智能體學習統計面板")
    print("=" * 80)
    print()

    learning_log = BASE_DIR / "logs" / "agent_learning_reflections.json"

    if not learning_log.exists():
        print("📝 尚無學習記錄，請進行對話後重試")
        return

    try:
        # 讀取所有學習記錄
        records = []
        with open(learning_log, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except:
                        pass

        if not records:
            print("📝 尚無有效的學習記錄")
            return

        # 1. 總體統計
        print("📈 總體統計")
        print("-" * 80)
        total_sessions = len(records)
        total_rounds = sum(r.get("rounds", 0) for r in records)
        avg_quality = (
            sum(r.get("quality_score", 0) for r in records) / total_sessions
            if total_sessions > 0
            else 0
        )

        print(f"總對話場次: {total_sessions} 場")
        print(f"累積對話回合數: {total_rounds} 回合")
        print(f"平均質量評分: {avg_quality:.0f}/100")

        # 2. 主題統計
        print("\n🎯 學習主題統計")
        print("-" * 80)

        topic_counter = Counter()
        for record in records:
            topics = record.get("topics", [])
            for topic in topics:
                topic_counter[topic] += 1

        if topic_counter:
            sorted_topics = sorted(
                topic_counter.items(), key=lambda x: x[1], reverse=True
            )
            for topic, count in sorted_topics:
                bar = "█" * count
                print(f"{topic:15} | {bar} ({count} 次)")
        else:
            print("暫無主題數據")

        # 3. 最近的對話記錄
        print("\n📋 最近對話回顧")
        print("-" * 80)

        for i, record in enumerate(records[-5:], 1):
            timestamp = record.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(timestamp)
                display_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                display_time = timestamp

            rounds = record.get("rounds", 0)
            quality = record.get("quality_score", 0)
            topics = ", ".join(record.get("topics", []))

            print(f"\n{i}. [{display_time}]")
            print(f"   回合數: {rounds} | 質量: {quality}/100")
            print(f"   主題: {topics if topics else '無'}")

        # 4. 改進建議（最新）
        print("\n🚀 最新學習建議")
        print("-" * 80)

        latest_record = records[-1]
        suggestions = latest_record.get("next_steps", [])

        for suggestion in suggestions:
            print(f"  {suggestion}")

        # 5. 趨勢分析
        if len(records) >= 2:
            print("\n📊 趨勢分析")
            print("-" * 80)

            quality_trend = [r.get("quality_score", 0) for r in records]
            rounds_trend = [r.get("rounds", 0) for r in records]

            if quality_trend:
                quality_change = quality_trend[-1] - quality_trend[0]
                direction = (
                    "📈 上升"
                    if quality_change > 0
                    else "📉 下降"
                    if quality_change < 0
                    else "➡️  穩定"
                )
                print(f"質量評分趨勢: {direction} ({quality_change:+.0f})")

            if rounds_trend:
                avg_rounds_early = (
                    sum(rounds_trend[: len(rounds_trend) // 2])
                    / (len(rounds_trend) // 2)
                    if len(rounds_trend) > 1
                    else 0
                )
                avg_rounds_recent = (
                    sum(rounds_trend[len(rounds_trend) // 2 :])
                    / (len(rounds_trend) - len(rounds_trend) // 2)
                    if len(rounds_trend) > 1
                    else 0
                )

                if avg_rounds_recent > avg_rounds_early:
                    print(f"✅ 對話長度在增加，表現深度思考")
                elif avg_rounds_recent < avg_rounds_early:
                    print(f"📌 對話長度在減少，可嘗試提出更複雜的問題")

        print()

    except Exception as e:
        print(f"❌ 讀取失敗: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    display_learning_dashboard()

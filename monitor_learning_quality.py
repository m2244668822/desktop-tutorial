#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體實時學習監控儀表板
- 實時追蹤背景學習進度
- 監控對話品質與深度
- 自動計算優化指標
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent


def get_latest_session():
    """獲取最新會話"""
    session_dir = BASE_DIR / "data" / "conversation_logs"
    sessions = sorted(session_dir.glob("groq_session_*.json"))
    return sessions[-1] if sessions else None


def analyze_learning_quality(session_path):
    """分析會話品質"""
    try:
        with open(session_path, encoding="utf-8") as f:
            data = json.load(f)
    except:
        return None

    extractions = data.get("learning_extractions", [])
    if not extractions:
        return None

    # 計算品質指標
    metrics = {
        "total_extractions": len(extractions),
        "topics": defaultdict(int),
        "avg_key_points": 0,
        "quality_score": 0,
    }

    total_points = 0
    high_quality_count = 0

    for ext in extractions:
        topic = ext.get("topic", "未分類")
        metrics["topics"][topic] += 1

        key_points = ext.get("key_points", [])
        total_points += len(key_points)

        # 品質評估
        if len(key_points) >= 2 and ext.get("topic") != "未分類":
            high_quality_count += 1

    if extractions:
        metrics["avg_key_points"] = total_points / len(extractions)
        metrics["quality_score"] = min(
            100, int((high_quality_count / len(extractions)) * 100)
        )

    return metrics


def count_learning_rounds():
    """統計學習輪數"""
    log_file = BASE_DIR / "logs" / "autonomous_learning_background.log"
    if not log_file.exists():
        return 0

    with open(log_file) as f:
        content = f.read()

    return content.count("🧠 第")


def display_dashboard():
    """顯示實時儀表板"""
    latest_session = get_latest_session()
    if not latest_session:
        print("❌ 找不到會話")
        return

    metrics = analyze_learning_quality(latest_session)
    rounds = count_learning_rounds()

    print("\n" + "=" * 80)
    print("  📊 智能體實時學習監控儀表板")
    print("=" * 80)
    print(f"\n⏱️ 檢查時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 基礎統計
    print(f"\n📈 學習進度")
    print("-" * 80)
    print(f"已完成輪數: {rounds} 輪" + (" 🟢" if rounds >= 10 else " 🟡"))
    print(f"最新會話: {latest_session.name}")

    if metrics:
        # 品質指標
        print(f"\n✅ 對話品質")
        print("-" * 80)
        print(f"提取筆數: {metrics['total_extractions']} 筆")
        print(f"平均重點數/筆: {metrics['avg_key_points']:.1f}")
        print(
            f"質量評分: {metrics['quality_score']}/100 "
            + ("✅" if metrics["quality_score"] >= 70 else "🟡")
        )

        # 主題分佈
        print(f"\n🎯 主題分佈")
        print("-" * 80)
        for topic, count in sorted(metrics["topics"].items(), key=lambda x: -x[1]):
            bar = "█" * min(count, 15)
            print(f"{topic:20} {bar} {count}")

        # 深度評估
        print(f"\n🔍 對話深度評估")
        print("-" * 80)
        if rounds >= 3:
            print(f"✅ 已進入深化學習階段（3+ 輪同主題）")
        if rounds >= 7:
            print(f"✅ 已完成 2 個完整周期（7+ 輪）")
        if rounds >= 10:
            print(f"✅ 已進入穩定學習階段（10+ 輪）")

        # 優化方向
        print(f"\n🚀 當前優化方向")
        print("-" * 80)
        recommendations = []

        if metrics["quality_score"] < 50:
            recommendations.append("提升主題識別準確度（減少'未分類'）")
        if metrics["avg_key_points"] < 2:
            recommendations.append("增加每筆提取的關鍵詞深度")
        if len(metrics["topics"]) < 3:
            recommendations.append("均衡三大主題的學習比例")

        if recommendations:
            for rec in recommendations[:2]:
                print(f"• {rec}")
        else:
            print("✅ 所有指標在正常範圍內，持續學習中...")

    # 實時建議
    print(f"\n💡 實時建議")
    print("-" * 80)
    if rounds >= 20:
        print("✅ 已積累充足學習數據，可執行性能評估")
        print("   建議: python3 agent_performance_optimization.py")
    elif rounds >= 10:
        print(f"✅ {rounds} 輪完成，已開始形成知識框架")
        print("   繼續學習可進一步優化對話品質")
    else:
        print(f"學習中... {rounds}/10 完成基礎周期")

    print("\n" + "=" * 80 + "\n")


def continuous_monitor(interval: int = 10):
    """持續監控"""
    print(f"\n🔍 進入連續監控模式（每 {interval} 秒更新一次）")
    print("   按 Ctrl+C 退出\n")

    try:
        round_count = 0
        while True:
            display_dashboard()
            round_count += 1
            print(f"⏳ 等待 {interval} 秒後下次更新... (第 {round_count} 次檢查)")
            for i in range(interval):
                sys.stdout.write(f"\r  進度: {i + 1}/{interval}")
                sys.stdout.flush()
                time.sleep(1)
            sys.stdout.write("\r" + " " * 20 + "\r")
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n\n👋 已停止監控")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        continuous_monitor(interval)
    else:
        display_dashboard()

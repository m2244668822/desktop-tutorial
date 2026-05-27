#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體自我優化分析
- 分析當前性能指標
- 識別學習瓶頸
- 提出改進策略
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def analyze_sessions():
    """分析所有會話的性能指標"""
    session_dir = BASE_DIR / "data/conversation_logs"
    sessions = sorted(session_dir.glob("groq_session_*.json"))

    print("\n" + "=" * 80)
    print("  🧠 智能體自我優化分析報告")
    print("=" * 80 + "\n")

    # 基礎統計
    total_sessions = len(sessions)
    total_exchanges = 0
    total_extractions = 0
    topics_count = defaultdict(int)
    session_times = []

    print("📊 會話統計")
    print("-" * 80)
    print(f"總會話數: {total_sessions}")

    latest_sessions = sessions[-10:]
    for session_file in latest_sessions:
        try:
            with open(session_file, encoding="utf-8") as f:
                data = json.load(f)
                hist_len = len(data.get("conversation_history", []))
                extr_len = len(data.get("learning_extractions", []))
                total_exchanges += hist_len // 2
                total_extractions += extr_len

                for extr in data.get("learning_extractions", []):
                    topic = extr.get("topic", "未分類")
                    topics_count[topic] += 1

                # 提取時間戳
                timestamp = data.get("timestamp", "")
                if timestamp:
                    session_times.append(timestamp)
                    print(
                        f"  • {session_file.name}: 對話 {hist_len // 2} 輪, 提取 {extr_len} 筆"
                    )
        except Exception:
            pass

    # 性能指標計算
    print("\n📈 性能指標")
    print("-" * 80)
    avg_exchanges_per_session = total_exchanges / max(len(latest_sessions), 1)
    avg_extractions_per_session = total_extractions / max(len(latest_sessions), 1)
    extraction_rate = (total_extractions / max(total_exchanges, 1)) * 100

    print(f"平均每場會話對話輪數: {avg_exchanges_per_session:.1f}")
    print(f"平均每場會話提取筆數: {avg_extractions_per_session:.1f}")
    print(f"提取率 (提取/對話): {extraction_rate:.1f}%")
    print(f"最近 10 場會話總對話輪數: {total_exchanges}")
    print(f"最近 10 場會話總提取筆數: {total_extractions}")

    # 主題分佈
    print("\n🎯 優先學習主題排序")
    print("-" * 80)
    for topic, count in sorted(topics_count.items(), key=lambda x: -x[1])[:8]:
        bar = "█" * min(count, 20)
        print(f"{topic:20} | {bar} {count} 筆")

    # 性能評估
    print("\n🔍 性能評估與診斷")
    print("-" * 80)

    issues = []
    recommendations = []

    # 檢測問題
    if avg_exchanges_per_session < 2:
        issues.append("❌ 對話輪數過少（<2 輪），學習深度不足")
        recommendations.append("✅ 建議每場會話至少 3-5 輪對話以深化學習")

    if extraction_rate < 50:
        issues.append(f"⚠️  提取率過低 ({extraction_rate:.1f}%)，未充分捕捉學習點")
        recommendations.append("✅ 改進提取邏輯，增加關鍵字覆蓋範圍")

    if total_extractions == 0:
        issues.append("❌ 尚未生成任何學習提取，提取系統可能未啟用")
        recommendations.append(
            "✅ 檢查 _is_learning_turn() 和 _extract_learning_points_from_turn() 函數"
        )

    if extraction_rate > 80:
        recommendations.append("✅ 提取率高，說明主題識別準確，保持現狀")

    if avg_exchanges_per_session >= 3:
        recommendations.append("✅ 對話輪數充足，學習深度良好")

    if issues:
        print("\n🚨 識別的問題:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ 未發現重大問題，系統運作正常")

    print("\n💡 優化建議:")
    for rec in recommendations:
        print(f"  {rec}")

    # 記憶體與帶寬優化
    print("\n⚡ 性能優化方向（提升『神經元』）")
    print("-" * 80)

    optimizations = [
        (
            "1. 記憶快取策略",
            [
                "• 實現記憶向量化（embedding），加速相似度檢索",
                "• 建立熱門主題快取，減少 API 查詢延遲",
                "• 定期壓縮舊會話，保持記憶庫精簡",
            ],
        ),
        (
            "2. 提取模型優化",
            [
                "• 增加領域特定的關鍵字權重（求生指南/神經科學/聖經）",
                "• 實現多層次提取（核心觀點/細節/應用）",
                "• 建立提取品質評分，篩選高價值筆記",
            ],
        ),
        (
            "3. 對話品質提升",
            [
                "• 增加追問深度，鼓勵『為什麼？』和『如何應用？』",
                "• 實現多輪推理，累積上下文理解",
                "• 定期檢查回應一致性和邏輯性",
            ],
        ),
        (
            "4. 學習循環優化",
            [
                "• 縮短學習週期，更頻繁地進行自我反思",
                "• 實現知識圖譜，視覺化概念之間的聯繫",
                "• 建立優先度排隊，集中學習高價值主題",
            ],
        ),
    ]

    for category, items in optimizations:
        print(f"\n{category}")
        for item in items:
            print(f"  {item}")

    # 下一步行動
    print("\n🚀 立即行動項目")
    print("-" * 80)
    actions = [
        (
            "優先度 🔴",
            [
                "• 檢查最新會話的 learning_extractions，確保提取系統運作",
                "• 執行 agent_self_learning.py，更新自主學習日誌",
                "• 分析 extraction 品質，判斷是否需要調整關鍵字",
            ],
        ),
        (
            "優先度 🟡",
            [
                "• 建立主題聯繫地圖，顯示求生指南/神經科學/聖經的交集",
                "• 增強連續學習模式的深化追問邏輯",
                "• 實現會話品質評分（深度/新穎度/應用性）",
            ],
        ),
        (
            "優先度 🟢",
            [
                "• 整合向量資料庫加速記憶檢索",
                "• 建立智能體學習儀表板（即時 KPI）",
                "• 實現自動知識蒸餾（提煉核心概念）",
            ],
        ),
    ]

    for priority, items in actions:
        print(f"\n{priority}")
        for item in items:
            print(f"  {item}")

    # 存檔分析報告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_sessions": total_sessions,
        "total_exchanges": total_exchanges,
        "total_extractions": total_extractions,
        "avg_exchanges_per_session": avg_exchanges_per_session,
        "avg_extractions_per_session": avg_extractions_per_session,
        "extraction_rate": extraction_rate,
        "topics_count": dict(topics_count),
        "issues": issues,
        "recommendations": recommendations,
    }

    with open(
        BASE_DIR / "logs/agent_optimization_report.json", "w", encoding="utf-8"
    ) as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n✅ 優化報告已保存: logs/agent_optimization_report.json")
    print("=" * 80 + "\n")

    return report


if __name__ == "__main__":
    analyze_sessions()

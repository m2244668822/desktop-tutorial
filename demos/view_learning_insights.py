#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面学习洞察查看器
查看中枢神经系统整合的所有学习数据
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

from autonomous_agent import autonomous_agent


def main():
    print("\n" + "=" * 80)
    print("🧠 中樞神經 - 全面學習洞察")
    print("=" * 80)
    print()

    # 菜单选项
    print("請選擇查看選項：")
    print("1. 完整學習報告（推薦）")
    print("2. 學習洞察（JSON 格式）")
    print("3. 系統優化建議")
    print("4. 協作系統狀態")
    print("0. 退出")

    choice = input("\n請輸入選項 (0-4): ").strip()

    if choice == "1":
        print("\n" + "=" * 80)
        print("📊 生成完整學習報告...")
        print("=" * 80)
        report = autonomous_agent.generate_learning_report()
        print(report)

    elif choice == "2":
        print("\n" + "=" * 80)
        print("🔍 獲取學習洞察...")
        print("=" * 80)
        insights = autonomous_agent.get_comprehensive_learning_insights()

        import json

        print(json.dumps(insights, ensure_ascii=False, indent=2))

    elif choice == "3":
        print("\n" + "=" * 80)
        print("💡 系統優化建議")
        print("=" * 80)
        recommendations = autonomous_agent.get_system_recommendations()

        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                priority_emoji = (
                    "🔴"
                    if rec["priority"] == "high"
                    else "🟡"
                    if rec["priority"] == "medium"
                    else "🟢"
                )
                print(f"\n{i}. {priority_emoji} {rec['title']} [{rec['category']}]")
                print(f"   {rec['description']}")
                print(f"   建議行動: {rec['action']}")
        else:
            print("✅ 沒有優化建議，系統運行良好！")

    elif choice == "4":
        print("\n" + "=" * 80)
        print("🤝 協作系統狀態")
        print("=" * 80)
        status = autonomous_agent.get_collaboration_status()

        print(f"\n中樞神經狀態: {status['central_nervous']['status']}")
        print(
            f"協調的智能體: {len(status['central_nervous']['coordinating_agents'])} 個"
        )
        print(f"待處理消息: {status['message_queue']['pending_messages']} 條")
        print(f"消息歷史: {status['message_queue']['total_history']} 條")
        print(f"協作洞察: {status['collaboration_insights']} 個")
        print(f"待處理建議: {status['pending_suggestions']} 個")

        print("\n註冊的智能體:")
        for agent in status["central_nervous"]["coordinating_agents"]:
            print(f"  • {agent}")

    elif choice == "0":
        print("\n👋 再見！")

    else:
        print("\n❌ 無效選項")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback

        traceback.print_exc()

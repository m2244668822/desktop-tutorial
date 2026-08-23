"""
智能體協作系統演示 - Multi-Agent Collaboration Demo
展示中樞神經與代碼更新智能體的互動與自主學習
"""

from autonomous_agent import autonomous_agent
from code_updater_agent import code_updater_agent
from agent_communication import (
    message_broker,
    collaboration_context,
    agent_registry,
    EventType,
)
import time


def demo_basic_collaboration():
    """演示 1: 基本協作 - 代碼分析與問題檢測"""
    print("\n" + "=" * 60)
    print("🎬 演示 1: 基本協作 - 代碼分析與問題檢測")
    print("=" * 60)

    print("\n📋 步驟 1: 代碼更新智能體開始分析代碼...")
    analysis = code_updater_agent.analyze_code()

    print(f"\n📊 分析結果:")
    print(f"   - 分析的文件: {len(analysis['files'])}")
    print(f"   - 發現的問題: {len(analysis['global_issues'])}")

    # 給時間讓事件被處理
    time.sleep(0.5)

    print("\n✨ 中樞神經已接收到代碼問題報告")


def demo_code_update_flow():
    """演示 2: 代碼更新工作流"""
    print("\n" + "=" * 60)
    print("🎬 演示 2: 代碼更新工作流")
    print("=" * 60)

    print("\n🔍 步驟 1: 分析代碼...")
    analysis = code_updater_agent.analyze_code()

    time.sleep(0.5)

    print("\n💡 步驟 2: 生成更新提案...")
    proposals = code_updater_agent.generate_update_proposal(analysis)

    print(f"   - 提案數量: {len(proposals['proposed_changes'])}")

    time.sleep(0.5)

    if proposals["proposed_changes"]:
        print("\n🔧 步驟 3: 執行第一個提案...")
        first_proposal = proposals["proposed_changes"][0]
        success, msg = code_updater_agent.execute_update(first_proposal)

    time.sleep(0.5)

    print("\n📊 步驟 4: 生成改進報告...")
    report = code_updater_agent.report_improvements()

    print(f"   - 總更新次數: {report['total_updates']}")
    print(f"   - 成功的更新: {report['successful_updates']}")
    print(f"   - 失敗的更新: {report['failed_updates']}")


def demo_learning_sharing():
    """演示 3: 學習數據共享"""
    print("\n" + "=" * 60)
    print("🎬 演示 3: 學習數據共享")
    print("=" * 60)

    print("\n🧠 中樞神經共享學習洞察...")
    autonomous_agent.share_learning_insights()

    time.sleep(0.5)

    print("\n📚 獲取所有共享的洞察:")
    insights = collaboration_context.get_all_insights()

    for i, insight in enumerate(insights[-3:], 1):  # 顯示最後 3 個
        print(f"\n   洞察 {i}:")
        print(f"      來源: {insight.get('from_agent')}")
        print(f"      時間: {insight.get('timestamp')}")


def demo_agent_communication():
    """演示 4: 智能體通信"""
    print("\n" + "=" * 60)
    print("🎬 演示 4: 智能體間的通信")
    print("=" * 60)

    print("\n📢 中樞神經發起代碼分析請求...")
    autonomous_agent.request_code_analysis()

    time.sleep(1)

    print("\n📊 消息歷史:")
    recent_messages = message_broker.get_recent_messages(limit=5)

    for msg in recent_messages[-5:]:
        print(f"   - {msg['timestamp']}: {msg['sender']} → {msg['receiver']}")
        print(f"     事件: {msg['event_type']}")


def demo_collaboration_status():
    """演示 5: 協作系統狀態"""
    print("\n" + "=" * 60)
    print("🎬 演示 5: 協作系統整體狀態")
    print("=" * 60)

    status = autonomous_agent.get_collaboration_status()

    print("\n🔗 已註冊的智能體:")
    for agent in status["central_nervous"]["coordinating_agents"]:
        agent_info = agent_registry.get_agent_info(agent)
        print(f"   - {agent}")
        print(f"     類型: {agent_info['type']}")
        print(f"     能力: {', '.join(agent_info['capabilities'])}")

    print(f"\n📨 消息隊列狀態:")
    print(f"   - 待處理消息: {status['message_queue']['pending_messages']}")
    print(f"   - 消息歷史: {status['message_queue']['total_history']}")

    print(f"\n💡 協作洞察:")
    print(f"   - 共享洞察: {status['collaboration_insights']}")
    print(f"   - 待處理建議: {status['pending_suggestions']}")


def demo_feedback_improvement():
    """演示 6: 反饋驅動的改進"""
    print("\n" + "=" * 60)
    print("🎬 演示 6: 反饋系統與自動改進")
    print("=" * 60)

    print("\n⭐ 提交模型反饋...")

    # 模擬一些反饋
    autonomous_agent.submit_feedback("ollama", 88, "response_001")
    time.sleep(0.2)
    autonomous_agent.submit_feedback("gemini", 92, "response_002")
    time.sleep(0.2)
    autonomous_agent.submit_feedback("openai", 75, "response_003")

    time.sleep(0.5)

    print("\n📊 反饋統計:")
    feedback_stats = autonomous_agent.get_feedback_statistics()

    for model, stats in feedback_stats.items():
        if stats.get("has_feedback"):
            print(f"   {model}:")
            print(f"      平均評分: {stats['平均評分']}")
            print(f"      質量等級: {stats['質量等級']}")

    time.sleep(0.5)

    print("\n🔄 根據反饋調整模型選擇...")
    autonomous_agent.adjust_model_selection_by_feedback()


def main():
    """主演示函數"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  🤖 智能體協作系統演示  ".center(58) + "║")
    print("║" + "  中樞神經 × 代碼更新智能體自主學習系統  ".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")

    try:
        # 運行各個演示
        demo_basic_collaboration()
        time.sleep(1)

        demo_code_update_flow()
        time.sleep(1)

        demo_learning_sharing()
        time.sleep(1)

        demo_agent_communication()
        time.sleep(1)

        demo_collaboration_status()
        time.sleep(1)

        demo_feedback_improvement()

    except Exception as e:
        print(f"\n❌ 演示出錯: {e}")
        import traceback

        traceback.print_exc()

    # 最終狀態報告
    print("\n" + "=" * 60)
    print("✅ 演示完成!")
    print("=" * 60)

    final_status = autonomous_agent.get_collaboration_status()

    print(f"\n📊 最終系統狀態:")
    print(
        f"   - 活動智能體: {len(final_status['central_nervous']['coordinating_agents'])}"
    )
    print(f"   - 消息交換總量: {final_status['message_queue']['total_history']}")
    print(f"   - 共享洞察: {final_status['collaboration_insights']}")
    print(f"   - 待處理改進建議: {final_status['pending_suggestions']}")

    print("\n" + "=" * 60)
    print("💡 什麼是智能體協作系統?")
    print("=" * 60)
    print("""
中樞神經 (Central Nervous System):
  ✓ 管理模型的健康狀態和性能評分
  ✓ 做出智能模型選擇和故障轉移決策
  ✓ 收集和分析反饋數據
  ✓ 協調其他專業智能體的工作
  ✓ 共享學習洞察

代碼更新智能體 (Code Updater Agent):
  ✓ 分析代碼結構和檢測問題
  ✓ 生成代碼改進提案
  ✓ 執行代碼更新
  ✓ 測試代碼變更
  ✓ 生成改進報告

協作通信層 (Agent Communication Layer):
  ✓ 事件發布/訂閱系統
  ✓ 消息隊列和歷史記錄
  ✓ 協作上下文的共享
  ✓ 智能體註冊表管理

優勢:
  🎯 誰都可以發起代碼分析請求
  🎯 自動檢測系統問題並主動改進
  🎯 所有學習數據跨智能體共享
  🎯 模塊化設計，易於添加新的專業智能體
  🎯 自主學習能力不斷提升
    """)


if __name__ == "__main__":
    main()

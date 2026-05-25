#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一学习系统快速演示
展示中枢神经的全面学习能力
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

from autonomous_agent import autonomous_agent


def demo():
    print("\n" + "🌟" * 40)
    print("   统一学习系统 - 快速演示")
    print("🌟" * 40 + "\n")

    # 演示1: 系统健康评分
    print("1️⃣  系统健康评分")
    print("-" * 60)
    insights = autonomous_agent.get_comprehensive_learning_insights()
    health = insights["system_health"]
    print(f"   健康评分: {health['health_score']}/100")
    print(f"   状态: {health['status'].upper()}")
    if health["issues"]:
        print(f"   问题: {len(health['issues'])} 个")
    else:
        print("   问题: 无 ✅")

    # 演示2: 数据源统计
    print("\n2️⃣  数据源统计")
    print("-" * 60)
    ds = insights["data_sources"]
    print(f"   对话记录: {ds['conversations']['total']} 条")
    print(f"   编程会话: {ds['learning_log']['programming_sessions']} 个")
    print(f"   学习笔记: {ds['learning_log']['learning_notes']} 条")
    print(f"   文件追踪: {ds['filesystem']['total_files_tracked']} 个")

    # 演示3: 模型性能
    print("\n3️⃣  模型性能分析")
    print("-" * 60)
    mp = insights["model_performance"]
    if mp.get("status") != "no_data":
        print(f"   总API调用: {mp['total_api_calls']}")
        print(f"   整体成功率: {mp['overall_success_rate']}%")
        print(f"   最佳模型: {mp.get('best_performing_model', '无')}")

        # 显示前3个模型
        models = list(mp["models"].items())[:3]
        for model, stats in models:
            status = "✅" if stats["health_status"] else "⚠️"
            print(
                f"   {status} {model}: {stats['success_rate']}% "
                f"({stats['success_count']}/{stats['total_calls']})"
            )

    # 演示4: 检测到的模式
    print("\n4️⃣  智能模式检测")
    print("-" * 60)
    patterns = insights["patterns_detected"]
    if patterns:
        for pattern in patterns[:3]:  # 只显示前3个
            print(f"   • {pattern['description']}")
            print(f"     置信度: {pattern['confidence']}")
    else:
        print("   暂无检测到的模式")

    # 演示5: 优化建议
    print("\n5️⃣  系统优化建议")
    print("-" * 60)
    recommendations = insights["recommendations"]
    if recommendations:
        for i, rec in enumerate(recommendations[:3], 1):  # 只显示前3个
            priority_emoji = (
                "🔴"
                if rec["priority"] == "high"
                else "🟡"
                if rec["priority"] == "medium"
                else "🟢"
            )
            print(f"   {priority_emoji} {rec['title']}")
            print(f"      {rec['description'][:60]}...")
    else:
        print("   ✅ 没有优化建议，系统运行良好！")

    # 演示6: 对话分析
    print("\n6️⃣  对话活跃度")
    print("-" * 60)
    ci = insights["conversation_insights"]
    if ci.get("status") != "no_data":
        print(f"   总对话: {ci['total_conversations']} 次")
        print(f"   总消息: {ci['total_messages']} 条")
        print(f"   最近7天: {ci['recent_conversations_7days']} 次")
        if ci.get("top_tags"):
            top_tag = ci["top_tags"][0]
            print(f"   热门标签: {top_tag[0]} ({top_tag[1]}次)")

    # 演示7: 代码学习
    print("\n7️⃣  代码学习统计")
    print("-" * 60)
    cl = insights["code_learning"]
    if cl.get("status") != "no_data":
        print(f"   编程会话: {cl['total_programming_sessions']} 个")
        print(f"   代码变更: {cl['total_code_changes']} 次")
        print(f"   学习要点: {cl['total_learnings_captured']} 条")
        if cl.get("most_changed_files"):
            most_changed = cl["most_changed_files"][0]
            print(
                f"   最常修改: {most_changed['file']} ({most_changed['change_count']}次)"
            )

    print("\n" + "🌟" * 40)
    print("\n💡 提示: 运行 'python view_learning_insights.py' 查看完整报告")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        demo()
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()

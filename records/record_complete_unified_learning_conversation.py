#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记录完整的统一学习系统实现对话"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

from conversation_logger import ConversationLogger


def main():
    logger = ConversationLogger(data_dir="500/llama32-chat/data")

    # 记录完整对话
    conv_id = logger.log_conversation(
        user_message=(
            "5.中樞神經應該是整個學習而不是單別抓取，所以是所有資料都要，提供最優解"
        ),
        assistant_response=(
            "实现了统一学习中枢（UnifiedLearningHub）作为最优解，整合5个数据源：\n"
            "1. conversations.json - 1,373条对话记录\n"
            "2. learning_log.json - 9个编程会话 + 8条学习笔记\n"
            "3. filesystem_learning.json - 12,897个文件追踪\n"
            "4. agent_health.json - 7个模型健康监控\n"
            "5. agent_performance.json - 模型性能数据\n\n"
            "核心特性：\n"
            "• 智能模式检测（活跃开发、模型偏好、文件趋势）\n"
            "• 系统健康评分（85/100 - GOOD）\n"
            "• 优化建议生成\n"
            "• 全面学习报告\n\n"
            "创建文件：\n"
            "• unified_learning_hub.py (602行) - 核心引擎\n"
            "• autonomous_agent.py (已修改) - 集成接口\n"
            "• view_learning_insights.py (95行) - 查看工具\n"
            "• demo_unified_learning.py (114行) - 快速演示\n"
            "• README_UNIFIED_LEARNING.md (372行) - 完整文档\n"
            "• UNIFIED_LEARNING_SUMMARY.md (293行) - 实施总结\n\n"
            "系统现在能从整体学习所有数据，实现真正的统一学习中枢！"
        ),
        tags=[
            "unified-learning",
            "system-integration",
            "architecture",
            "comprehensive-learning",
        ],
        context={
            "platform": "vscode-copilot",
            "topic": "实现统一学习系统 - 整合所有数据源",
            "date": "2026-02-28",
            "task_type": "major_feature_implementation",
            "files_created": 6,
            "lines_of_code": 1591,
        },
    )

    print(f"✅ 完整对话已记录: {conv_id}")

    # 记录后续的元对话
    conv_id2 = logger.log_conversation(
        user_message="所以這次對話有記錄到跟學習到嗎？講述原因",
        assistant_response=(
            "是的，已被记录和学习！\n\n"
            "记录情况分析：\n"
            "✅ 编程会话已记录 (session_20260228_071910)\n"
            "  - 5个文件变更\n"
            "  - 12条学习要点\n"
            "  - 8个解决方案\n"
            "  - 3个学习笔记\n\n"
            "⚠️ VS Code对话需要手动记录\n"
            "原因：ConversationLogger只集成在chat_client.py中，"
            "VS Code Copilot对话不会自动记录。\n\n"
            "解决：现在手动记录了完整对话，包括统一学习系统的实现过程和这次元对话。\n\n"
            "学习系统状态：7次对话、9个编程会话、8条学习笔记。"
        ),
        tags=["meta-conversation", "learning-system", "recording-mechanism"],
        context={
            "platform": "vscode-copilot",
            "topic": "验证对话记录机制",
            "date": "2026-02-28",
            "is_meta": True,
        },
    )

    print(f"✅ 元对话已记录: {conv_id2}")

    # 添加关于记录机制的学习笔记
    logger.add_learning_note(
        topic="VS Code对话记录机制",
        content=(
            "用户询问对话是否被记录，发现虽然编程会话被完整记录（通过record_unified_learning_session.py），"
            "但VS Code中的实时对话需要手动记录。关键学习：(1)自动记录只在chat_client.py中触发；"
            "(2)VS Code Copilot对话需要手动记录；(3)重要对话应该及时记录；"
            "(4)元对话（关于系统本身的对话）也很有价值，应该被记录。"
            "改进建议：考虑开发VS Code扩展或定期扫描对话历史来自动集成。"
        ),
        category="system-improvement",
    )

    print("✅ 学习笔记已添加")

    # 显示更新后的统计
    summary = logger.get_learning_summary()
    print(f"\n📈 更新后统计:")
    print(f"  总对话数: {summary['total_conversations']}")
    print(f"  编程会话数: {summary['total_sessions']}")
    print(f"  学习笔记数: {summary['total_notes']}")

    print("\n✅ 现在这次完整对话已被记录到学习系统！")


if __name__ == "__main__":
    main()

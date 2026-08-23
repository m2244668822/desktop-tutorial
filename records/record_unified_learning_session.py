#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记录统一学习系统开发会话"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

from conversation_logger import ConversationLogger


def main():
    logger = ConversationLogger(data_dir="500/llama32-chat/data")

    # 记录编程会话
    session_id = logger.log_programming_session(
        task_description="实现中枢神经统一学习系统 - 整合所有数据源进行全面学习",
        code_changes=[
            {
                "file": "500/llama32-chat/unified_learning_hub.py",
                "description": "创建统一学习中枢 - 整合5个数据源（对话、学习日志、文件系统、模型健康、模型性能）",
            },
            {
                "file": "500/llama32-chat/autonomous_agent.py",
                "description": "集成统一学习中枢到中枢神经，添加全面洞察方法",
            },
            {
                "file": "view_learning_insights.py",
                "description": "创建学习洞察查看器 - 4个查看选项的便捷工具",
            },
            {
                "file": "demo_unified_learning.py",
                "description": "创建快速演示脚本 - 7个核心功能展示",
            },
            {
                "file": "README_UNIFIED_LEARNING.md",
                "description": "创建完整文档 - 系统架构、使用方法、最佳实践",
            },
        ],
        solutions=[
            "创建 UnifiedLearningHub 类整合所有数据源",
            "实现 get_comprehensive_insights() 方法进行全面分析",
            "实现 _detect_patterns() 智能检测跨数据源模式",
            "实现 _generate_recommendations() 生成优化建议",
            "实现 _analyze_system_health() 计算系统健康评分",
            "在 autonomous_agent 中添加统一学习接口",
            "创建便捷的命令行工具和演示脚本",
            "提供完整的文档和使用指南",
        ],
        learnings=[
            "数据整合的关键是统一接口 - 单一入口访问所有数据",
            "跨数据源分析能发现单一数据源无法发现的模式",
            "系统健康评分需要多维度综合评估（数据完整性、新鲜度、模型可用性）",
            "智能推荐需要基于实际数据而非假设",
            "用户体验：提供多种访问方式（CLI、API、演示）",
            "文档的重要性：详细的使用指南和最佳实践",
            "模式检测：对话与代码变更的时间相关性分析",
            "性能优化：延迟加载、缓存、增量更新",
            "86.7% 的文件未分类 - 显示系统还有很大学习空间",
            "最常修改文件反映了开发重点（chat_client.py 4次）",
            "模型使用偏好可以指导未来优化（gemini 100%成功率）",
            "活跃开发模式的识别：24小时内7次对话+8个编程会话",
        ],
    )

    print(f"✅ 编程会话已记录: {session_id}")

    # 添加学习笔记
    logger.add_learning_note(
        topic="统一学习系统架构",
        content=(
            "用户要求'中樞神經應該是整個學習而不是單別抓取，所以是所有資料都要，提供最優解'。"
            "实现了 UnifiedLearningHub 作为核心，整合5个数据源：conversations.json(1373条)、"
            "learning_log.json(8会话+5笔记)、filesystem_learning.json(12897文件)、"
            "agent_health.json(7模型)、agent_performance.json(5次调用)。"
            "关键特性：智能模式检测（活跃开发、模型偏好、文件趋势）、系统健康评分(85/100)、"
            "优化建议生成、可读报告输出。最优解的核心是'单一真相来源'原则 - "
            "所有学习数据统一管理、统一分析、统一输出，避免数据孤岛。"
        ),
        category="architecture",
    )

    logger.add_learning_note(
        topic="跨数据源模式检测",
        content=(
            "实现了3种智能模式检测：(1)对话-代码关联：检测24小时内的对话和编程会话同时活跃，"
            "表明活跃开发状态；(2)模型使用偏好：统计最常使用和最佳性能模型(gemini 100%)；"
            "(3)文件变化趋势：对比历史扫描记录检测文件数量增长(+4个新文件)。"
            "这些模式只有在整合多个数据源后才能发现，单一数据源无法实现。"
        ),
        category="data-analysis",
    )

    logger.add_learning_note(
        topic="系统健康评分算法",
        content=(
            "健康评分从100分开始扣分：数据源为空(-10/源)、模型不可用(-5/模型)、"
            "数据过时(-10)。当前评分85/100(GOOD)，1个问题(flesystem数据为0)。"
            "评分分级：excellent(90+)/good(70-89)/fair(50-69)/poor(<50)。"
            "这种评分机制提供了系统整体健康状态的量化指标，便于监控和预警。"
        ),
        category="system-monitoring",
    )

    # 显示统计
    summary = logger.get_learning_summary()
    print(f"\n📈 学习系统更新后统计:")
    print(f"  总对话数: {summary['total_conversations']}")
    print(f"  编程会话数: {summary['total_sessions']}")
    print(f"  学习笔记数: {summary['total_notes']}")

    print("\n✅ 所有学习数据已记录到系统")


if __name__ == "__main__":
    main()

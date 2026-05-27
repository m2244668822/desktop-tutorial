#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查这次对话是否被记录"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))

from conversation_logger import ConversationLogger

logger = ConversationLogger(data_dir="500/llama32-chat/data")
summary = logger.get_learning_summary()

print("=" * 80)
print("📊 学习系统当前状态")
print("=" * 80)
print(f"\n总对话数: {summary['total_conversations']}")
print(f"编程会话数: {summary['total_sessions']}")
print(f"学习笔记数: {summary['total_notes']}")

# 查看最近的记录
conv_file = os.path.join(
    os.path.dirname(__file__), "500/llama32-chat/data/conversations.json"
)
with open(conv_file, "r", encoding="utf-8") as f:
    convs = json.load(f)

print(f"\n最近5次对话:")
for conv in convs[-5:]:
    conv_id = conv.get("id", "unknown")
    timestamp = conv.get("timestamp", "")[:19]
    tags = conv.get("tags", [])
    messages = conv.get("messages", [])
    context = conv.get("context", {})

    print(f"\n  • {conv_id} ({timestamp})")
    print(f"    标签: {', '.join(tags) if tags else '无'}")
    print(f"    消息数: {len(messages)}")
    if context:
        topic = context.get("topic", context.get("platform", ""))
        if topic:
            print(f"    主题: {topic}")

log_file = os.path.join(
    os.path.dirname(__file__), "500/llama32-chat/data/learning_log.json"
)
with open(log_file, "r", encoding="utf-8") as f:
    logs = json.load(f)

print(f"\n最近3个编程会话:")
count = 0
for log in reversed(logs):
    if log.get("type") == "programming_session" and count < 3:
        log_id = log.get("id", "unknown")
        timestamp = log.get("timestamp", "")[:19]
        task = log.get("task", "")
        print(f"\n  • {log_id} ({timestamp})")
        print(f"    任务: {task[:80]}..." if len(task) > 80 else f"    任务: {task}")
        print(f"    代码变更: {len(log.get('code_changes', []))} 个")
        print(f"    学习要点: {len(log.get('learnings', []))} 条")
        count += 1

print("\n" + "=" * 80)
print("\n分析结果:")
print("=" * 80)

# 检查是否有关于统一学习系统的记录
unified_learning_recorded = False
for log in logs:
    if log.get("type") == "programming_session":
        task = log.get("task", "")
        if "统一学习" in task or "unified" in task.lower() or "整合所有数据" in task:
            unified_learning_recorded = True
            break

if unified_learning_recorded:
    print("✅ 统一学习系统开发会话已记录")
else:
    print("⚠️  统一学习系统开发会话未找到")

# 检查VS Code对话
vscode_convs = [
    c for c in convs if c.get("context", {}).get("platform") == "vscode-copilot"
]
print(f"\n✅ VS Code 对话记录: {len(vscode_convs)} 次")

print("\n" + "=" * 80)

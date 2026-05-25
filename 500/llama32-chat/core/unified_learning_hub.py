#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一学习中枢 (Unified Learning Hub)
中枢神经的核心学习系统 - 整合所有数据源进行全面学习
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from collections import defaultdict

from utils import JsonStorage, TimeHelper
from constants import DATA_DIR


class UnifiedLearningHub:
    """统一学习中枢 - 整合所有数据源的学习系统"""

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 数据源文件路径
        self.conversations_file = self.data_dir / "conversations.json"
        self.learning_log_file = self.data_dir / "learning_log.json"
        self.filesystem_learning_file = self.data_dir / "filesystem_learning.json"
        self.agent_health_file = self.data_dir / "agent_health.json"
        self.agent_performance_file = self.data_dir / "agent_performance.json"
        self.unified_insights_file = self.data_dir / "unified_insights.json"

        # 加载所有数据源
        self._load_all_data()

        print("✅ 统一学习中枢已初始化")

    def _load_all_data(self):
        """加载所有数据源"""
        self.conversations = JsonStorage.load(self.conversations_file, default=[])
        self.learning_log = JsonStorage.load(self.learning_log_file, default=[])
        self.filesystem_data = JsonStorage.load(
            self.filesystem_learning_file, default={}
        )
        self.agent_health = JsonStorage.load(self.agent_health_file, default={})
        self.agent_performance = JsonStorage.load(
            self.agent_performance_file, default={}
        )

    def get_comprehensive_insights(self) -> Dict[str, Any]:
        """获取全面的学习洞察 - 整合所有数据源"""

        insights = {
            "timestamp": TimeHelper.now_iso(),
            "data_sources": self._analyze_data_sources(),
            "conversation_insights": self._analyze_conversations(),
            "code_learning": self._analyze_code_learning(),
            "filesystem_insights": self._analyze_filesystem(),
            "model_performance": self._analyze_model_performance(),
            "patterns_detected": self._detect_patterns(),
            "recommendations": self._generate_recommendations(),
            "system_health": self._analyze_system_health(),
        }

        # 保存洞察
        JsonStorage.save(self.unified_insights_file, insights)

        return insights

    def _analyze_data_sources(self) -> Dict:
        """分析所有数据源状态"""
        return {
            "conversations": {
                "total": len(self.conversations),
                "source_file": str(self.conversations_file),
                "last_updated": self._get_file_mtime(self.conversations_file),
            },
            "learning_log": {
                "total_entries": len(self.learning_log),
                "programming_sessions": len(
                    [
                        l
                        for l in self.learning_log
                        if l.get("type") == "programming_session"
                    ]
                ),
                "learning_notes": len([l for l in self.learning_log if "topic" in l]),
                "source_file": str(self.learning_log_file),
                "last_updated": self._get_file_mtime(self.learning_log_file),
            },
            "filesystem": {
                "total_files_tracked": self.filesystem_data.get("total_files", 0),
                "categories": len(self.filesystem_data.get("file_categories", {})),
                "source_file": str(self.filesystem_learning_file),
                "last_updated": self._get_file_mtime(self.filesystem_learning_file),
            },
            "model_health": {
                "models_tracked": len(self.agent_health),
                "source_file": str(self.agent_health_file),
                "last_updated": self._get_file_mtime(self.agent_health_file),
            },
            "model_performance": {
                "models_tracked": len(self.agent_performance),
                "source_file": str(self.agent_performance_file),
                "last_updated": self._get_file_mtime(self.agent_performance_file),
            },
        }

    def _analyze_conversations(self) -> Dict:
        """深度分析对话数据"""
        if not self.conversations:
            return {"status": "no_data"}

        # 统计标签
        all_tags = []
        for conv in self.conversations:
            tags = conv.get("tags", [])
            all_tags.extend(tags)

        tag_counts = defaultdict(int)
        for tag in all_tags:
            tag_counts[tag] += 1

        # 时间分析
        recent_conversations = [
            c
            for c in self.conversations
            if self._is_recent(c.get("timestamp", ""), days=7)
        ]

        # 内容分析
        total_messages = sum(len(c.get("messages", [])) for c in self.conversations)

        return {
            "total_conversations": len(self.conversations),
            "total_messages": total_messages,
            "recent_conversations_7days": len(recent_conversations),
            "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[
                :10
            ],
            "most_active_period": self._find_most_active_period(self.conversations),
            "conversation_sources": self._count_sources(self.conversations, "source"),
        }

    def _analyze_code_learning(self) -> Dict:
        """分析代码学习和编程会话"""
        if not self.learning_log:
            return {"status": "no_data"}

        programming_sessions = [
            l for l in self.learning_log if l.get("type") == "programming_session"
        ]
        learning_notes = [l for l in self.learning_log if "topic" in l]

        # 统计代码变更
        total_code_changes = sum(
            len(s.get("code_changes", [])) for s in programming_sessions
        )

        # 统计学到的知识点
        all_learnings = []
        for session in programming_sessions:
            all_learnings.extend(session.get("learnings", []))

        # 统计笔记分类
        note_categories = defaultdict(int)
        for note in learning_notes:
            category = note.get("category", "general")
            note_categories[category] += 1

        return {
            "total_programming_sessions": len(programming_sessions),
            "total_learning_notes": len(learning_notes),
            "total_code_changes": total_code_changes,
            "total_learnings_captured": len(all_learnings),
            "note_categories": dict(note_categories),
            "recent_sessions_7days": len(
                [
                    s
                    for s in programming_sessions
                    if self._is_recent(s.get("timestamp", ""), days=7)
                ]
            ),
            "most_changed_files": self._find_most_changed_files(programming_sessions),
        }

    def _analyze_filesystem(self) -> Dict:
        """分析文件系统学习数据"""
        if not self.filesystem_data:
            return {"status": "no_data"}

        files = self.filesystem_data.get("files", {})

        # 分类统计
        category_counts = defaultdict(int)
        importance_distribution = defaultdict(int)

        for file_path, file_data in files.items():
            category = file_data.get("category", "unknown")
            importance = file_data.get("importance", 0)
            category_counts[category] += 1
            importance_distribution[importance] += 1

        # 清理建议统计
        cleanup_candidates = len(
            [f for f in files.values() if f.get("temporary", False)]
        )

        return {
            "total_files_analyzed": len(files),
            "category_distribution": dict(category_counts),
            "importance_distribution": dict(importance_distribution),
            "cleanup_candidates": cleanup_candidates,
            "scan_history": self.filesystem_data.get("scan_history", [])[
                -5:
            ],  # 最近5次扫描
            "largest_files": self._get_largest_files(files),
        }

    def _analyze_model_performance(self) -> Dict:
        """分析模型性能数据"""
        if not self.agent_performance:
            return {"status": "no_data"}

        model_stats = {}

        for model, perf in self.agent_performance.items():
            total_calls = perf.get("success_count", 0) + perf.get("failure_count", 0)
            success_rate = (
                (perf.get("success_count", 0) / total_calls * 100)
                if total_calls > 0
                else 0
            )

            avg_response_time = 0
            if perf.get("success_count", 0) > 0:
                avg_response_time = perf.get("total_response_time", 0) / perf.get(
                    "success_count", 1
                )

            model_stats[model] = {
                "total_calls": total_calls,
                "success_count": perf.get("success_count", 0),
                "failure_count": perf.get("failure_count", 0),
                "success_rate": round(success_rate, 2),
                "avg_response_time": round(avg_response_time, 3),
                "health_status": self.agent_health.get(model, {}).get(
                    "available", False
                ),
            }

        # 排序找出最佳模型
        best_model = max(
            model_stats.items(),
            key=lambda x: (x[1]["success_rate"], -x[1]["avg_response_time"]),
            default=(None, {}),
        )[0]

        return {
            "models": model_stats,
            "best_performing_model": best_model,
            "total_api_calls": sum(s["total_calls"] for s in model_stats.values()),
            "overall_success_rate": self._calculate_overall_success_rate(model_stats),
        }

    def _detect_patterns(self) -> List[Dict]:
        """检测跨数据源的模式和关联"""
        patterns = []

        # 模式1: 对话与代码变更的关联
        if self.conversations and self.learning_log:
            recent_convs = len(
                [
                    c
                    for c in self.conversations
                    if self._is_recent(c.get("timestamp", ""), days=1)
                ]
            )
            recent_sessions = len(
                [
                    l
                    for l in self.learning_log
                    if l.get("type") == "programming_session"
                    and self._is_recent(l.get("timestamp", ""), days=1)
                ]
            )

            if recent_convs > 0 and recent_sessions > 0:
                patterns.append(
                    {
                        "type": "conversation_code_correlation",
                        "description": f"检测到活跃开发：24小时内 {recent_convs} 次对话和 {recent_sessions} 个编程会话",
                        "confidence": "high",
                    }
                )

        # 模式2: 模型使用偏好
        if self.agent_performance:
            most_used = max(
                self.agent_performance.items(),
                key=lambda x: (
                    x[1].get("success_count", 0) + x[1].get("failure_count", 0)
                ),
                default=(None, {}),
            )[0]
            if most_used:
                patterns.append(
                    {
                        "type": "preferred_model",
                        "description": f"最常使用的模型: {most_used}",
                        "model": most_used,
                        "confidence": "high",
                    }
                )

        # 模式3: 文件系统变化趋势
        if self.filesystem_data.get("scan_history"):
            scan_history = self.filesystem_data.get("scan_history", [])
            if len(scan_history) >= 2:
                latest = scan_history[-1]
                previous = scan_history[-2]
                file_growth = latest.get("total_files", 0) - previous.get(
                    "total_files", 0
                )

                if file_growth > 10:
                    patterns.append(
                        {
                            "type": "rapid_file_growth",
                            "description": f"文件数量快速增长: +{file_growth} 个文件",
                            "file_count": file_growth,
                            "confidence": "medium",
                        }
                    )

        return patterns

    def _generate_recommendations(self) -> List[Dict]:
        """基于全面数据生成优化建议"""
        recommendations = []

        # 建议1: 对话记录优化
        if len(self.conversations) > 10000:
            recommendations.append(
                {
                    "priority": "medium",
                    "category": "data_management",
                    "title": "对话数据归档",
                    "description": f"对话记录已达 {len(self.conversations)} 条，建议归档旧数据",
                    "action": "执行数据归档，保留最近6个月的活跃数据",
                }
            )

        # 建议2: 模型优化
        if self.agent_performance:
            for model, perf in self.agent_performance.items():
                total = perf.get("success_count", 0) + perf.get("failure_count", 0)
                if total > 10:
                    success_rate = perf.get("success_count", 0) / total * 100
                    if success_rate < 70:
                        recommendations.append(
                            {
                                "priority": "high",
                                "category": "model_performance",
                                "title": f"{model} 性能告警",
                                "description": f"{model} 成功率仅 {success_rate:.1f}%，建议检查配置",
                                "action": f"检查 {model} API 配置和可用性",
                            }
                        )

        # 建议3: 文件系统清理
        if self.filesystem_data:
            cleanup_candidates = len(
                [
                    f
                    for f in self.filesystem_data.get("files", {}).values()
                    if f.get("temporary", False)
                ]
            )
            if cleanup_candidates > 100:
                recommendations.append(
                    {
                        "priority": "low",
                        "category": "filesystem",
                        "title": "文件系统清理",
                        "description": f"发现 {cleanup_candidates} 个可清理的临时文件",
                        "action": "运行文件系统清理工具",
                    }
                )

        # 建议4: 学习数据完整性
        recent_sessions = len(
            [
                l
                for l in self.learning_log
                if l.get("type") == "programming_session"
                and self._is_recent(l.get("timestamp", ""), days=7)
            ]
        )
        recent_convs = len(
            [
                c
                for c in self.conversations
                if self._is_recent(c.get("timestamp", ""), days=7)
            ]
        )

        if recent_convs > 10 and recent_sessions == 0:
            recommendations.append(
                {
                    "priority": "medium",
                    "category": "learning_system",
                    "title": "编程会话记录缺失",
                    "description": "最近有很多对话但没有编程会话记录",
                    "action": "确保代码变更正确记录到学习系统",
                }
            )

        return recommendations

    def _analyze_system_health(self) -> Dict:
        """分析整体系统健康状况"""
        health_score = 100
        issues = []

        # 检查数据源状态
        if not self.conversations:
            health_score -= 10
            issues.append("对话记录为空")

        if not self.learning_log:
            health_score -= 10
            issues.append("学习日志为空")

        if not self.filesystem_data:
            health_score -= 10
            issues.append("文件系统数据为空")

        # 检查模型健康
        if self.agent_health:
            unavailable_models = [
                m for m, h in self.agent_health.items() if not h.get("available", False)
            ]
            if unavailable_models:
                health_score -= len(unavailable_models) * 5
                issues.append(f"不可用的模型: {', '.join(unavailable_models)}")

        # 检查数据新鲜度
        data_staleness = self._check_data_staleness()
        if data_staleness["stale_data_sources"]:
            health_score -= 10
            issues.append(
                f"数据过时: {', '.join(data_staleness['stale_data_sources'])}"
            )

        return {
            "health_score": max(0, health_score),
            "status": "excellent"
            if health_score >= 90
            else "good"
            if health_score >= 70
            else "fair"
            if health_score >= 50
            else "poor",
            "issues": issues,
            "data_staleness": data_staleness,
        }

    # === 辅助方法 ===

    def _is_recent(self, timestamp_str: str, days: int = 7) -> bool:
        """检查时间戳是否在最近N天内"""
        try:
            if not timestamp_str:
                return False
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            cutoff = datetime.now() - timedelta(days=days)
            return ts > cutoff
        except:
            return False

    def _get_file_mtime(self, filepath: Path) -> Optional[str]:
        """获取文件修改时间"""
        try:
            if filepath.exists():
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                return mtime.isoformat()
        except:
            pass
        return None

    def _find_most_active_period(self, conversations: List[Dict]) -> str:
        """找出最活跃的时间段"""
        if not conversations:
            return "无数据"

        # 简化版：只统计日期
        dates = defaultdict(int)
        for conv in conversations:
            try:
                ts = conv.get("timestamp", "")
                date = ts.split("T")[0] if "T" in ts else ts[:10]
                dates[date] += 1
            except:
                continue

        if dates:
            most_active_date = max(dates.items(), key=lambda x: x[1])
            return f"{most_active_date[0]} ({most_active_date[1]} 次对话)"
        return "无法确定"

    def _count_sources(self, data_list: List[Dict], key: str) -> Dict:
        """统计数据来源"""
        sources = defaultdict(int)
        for item in data_list:
            source = item.get(key, "unknown")
            sources[source] += 1
        return dict(sources)

    def _find_most_changed_files(
        self, sessions: List[Dict], limit: int = 10
    ) -> List[Dict]:
        """找出最常变更的文件"""
        file_changes = defaultdict(int)

        for session in sessions:
            for change in session.get("code_changes", []):
                file = change.get("file", "unknown")
                file_changes[file] += 1

        sorted_files = sorted(file_changes.items(), key=lambda x: x[1], reverse=True)[
            :limit
        ]
        return [{"file": f, "change_count": c} for f, c in sorted_files]

    def _get_largest_files(self, files: Dict, limit: int = 10) -> List[Dict]:
        """获取最大的文件"""
        file_list = [
            {"path": k, "size": v.get("size", 0)}
            for k, v in files.items()
            if "size" in v
        ]
        sorted_files = sorted(file_list, key=lambda x: x["size"], reverse=True)[:limit]
        return sorted_files

    def _calculate_overall_success_rate(self, model_stats: Dict) -> float:
        """计算整体成功率"""
        total_success = sum(s["success_count"] for s in model_stats.values())
        total_calls = sum(s["total_calls"] for s in model_stats.values())

        if total_calls == 0:
            return 0.0
        return round((total_success / total_calls) * 100, 2)

    def _check_data_staleness(self, days_threshold: int = 7) -> Dict:
        """检查数据新鲜度"""
        stale_sources = []

        # 检查各个数据文件的修改时间
        files_to_check = {
            "conversations": self.conversations_file,
            "learning_log": self.learning_log_file,
            "filesystem": self.filesystem_learning_file,
        }

        for name, filepath in files_to_check.items():
            mtime_str = self._get_file_mtime(filepath)
            if mtime_str:
                if not self._is_recent(mtime_str, days=days_threshold):
                    stale_sources.append(name)

        return {"stale_data_sources": stale_sources, "threshold_days": days_threshold}

    def generate_learning_report(self) -> str:
        """生成可读的学习报告"""
        insights = self.get_comprehensive_insights()

        report_lines = [
            "=" * 80,
            "🧠 统一学习中枢 - 全面学习报告",
            "=" * 80,
            f"\n生成时间: {insights['timestamp']}",
            f"\n系统健康评分: {insights['system_health']['health_score']}/100 ({insights['system_health']['status'].upper()})",
        ]

        # 数据源概览
        report_lines.extend(["\n" + "=" * 80, "📊 数据源概览", "=" * 80])

        ds = insights["data_sources"]
        report_lines.append(f"\n✅ 对话记录: {ds['conversations']['total']} 条")
        report_lines.append(
            f"✅ 编程会话: {ds['learning_log']['programming_sessions']} 个"
        )
        report_lines.append(f"✅ 学习笔记: {ds['learning_log']['learning_notes']} 条")
        report_lines.append(
            f"✅ 文件追踪: {ds['filesystem']['total_files_tracked']} 个"
        )
        report_lines.append(f"✅ 模型监控: {ds['model_health']['models_tracked']} 个")

        # 对话洞察
        if insights["conversation_insights"].get("status") != "no_data":
            ci = insights["conversation_insights"]
            report_lines.extend(
                [
                    "\n" + "=" * 80,
                    "💬 对话分析",
                    "=" * 80,
                    f"\n总对话数: {ci['total_conversations']}",
                    f"总消息数: {ci['total_messages']}",
                    f"最近7天: {ci['recent_conversations_7days']} 次对话",
                    f"\n热门标签:",
                ]
            )
            for tag, count in ci.get("top_tags", [])[:5]:
                report_lines.append(f"  • {tag}: {count}次")

        # 代码学习
        if insights["code_learning"].get("status") != "no_data":
            cl = insights["code_learning"]
            report_lines.extend(
                [
                    "\n" + "=" * 80,
                    "💻 代码学习",
                    "=" * 80,
                    f"\n编程会话: {cl['total_programming_sessions']} 个",
                    f"代码变更: {cl['total_code_changes']} 次",
                    f"学习要点: {cl['total_learnings_captured']} 条",
                    f"最近7天会话: {cl['recent_sessions_7days']} 个",
                ]
            )

            if cl.get("most_changed_files"):
                report_lines.append("\n最常修改的文件:")
                for item in cl["most_changed_files"][:5]:
                    report_lines.append(f"  • {item['file']}: {item['change_count']}次")

        # 模型性能
        if insights["model_performance"].get("status") != "no_data":
            mp = insights["model_performance"]
            report_lines.extend(
                [
                    "\n" + "=" * 80,
                    "🤖 模型性能",
                    "=" * 80,
                    f"\n总API调用: {mp['total_api_calls']}",
                    f"整体成功率: {mp['overall_success_rate']}%",
                    f"最佳模型: {mp.get('best_performing_model', '无')}",
                ]
            )

            report_lines.append("\n各模型表现:")
            for model, stats in mp["models"].items():
                status = "✅" if stats["health_status"] else "⚠️"
                report_lines.append(
                    f"  {status} {model}: {stats['success_rate']}% "
                    f"({stats['success_count']}/{stats['total_calls']}) "
                    f"响应时间: {stats['avg_response_time']:.3f}s"
                )

        # 检测到的模式
        if insights["patterns_detected"]:
            report_lines.extend(["\n" + "=" * 80, "🔍 检测到的模式", "=" * 80])
            for i, pattern in enumerate(insights["patterns_detected"], 1):
                report_lines.append(
                    f"\n{i}. {pattern['description']} (置信度: {pattern['confidence']})"
                )

        # 优化建议
        if insights["recommendations"]:
            report_lines.extend(["\n" + "=" * 80, "💡 优化建议", "=" * 80])
            for i, rec in enumerate(insights["recommendations"], 1):
                priority_emoji = (
                    "🔴"
                    if rec["priority"] == "high"
                    else "🟡"
                    if rec["priority"] == "medium"
                    else "🟢"
                )
                report_lines.append(f"\n{i}. {priority_emoji} {rec['title']}")
                report_lines.append(f"   {rec['description']}")
                report_lines.append(f"   建议行动: {rec['action']}")

        # 系统健康问题
        if insights["system_health"]["issues"]:
            report_lines.extend(["\n" + "=" * 80, "⚠️  系统问题", "=" * 80])
            for issue in insights["system_health"]["issues"]:
                report_lines.append(f"  • {issue}")

        report_lines.append("\n" + "=" * 80)

        return "\n".join(report_lines)


# 创建全局实例
unified_learning_hub = UnifiedLearningHub()

if __name__ == "__main__":
    # 测试
    hub = UnifiedLearningHub()
    print(hub.generate_learning_report())

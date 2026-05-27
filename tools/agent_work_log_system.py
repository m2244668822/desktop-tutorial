#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體工作日誌系統 (AI Agent Work Log System)

功能：
1. 自動記錄智能體的每日工作
2. 追蹤任務完成情況
3. 記錄系統優化與改進
4. 生成工作進度報告
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class WorkLog:
    """工作日誌條目"""

    date: str  # ISO format date
    task_category: str  # resume, learning, revenue, platform, optimization
    task_name: str  # 任務名稱
    description: str  # 詳細描述
    status: str  # completed, in_progress, pending
    time_spent_minutes: int = 0  # 耗時（分鐘）
    results: Dict[str, Any] = None  # 結果數據
    learning_insights: List[str] = None  # 學習要點

    def __post_init__(self):
        if self.results is None:
            self.results = {}
        if self.learning_insights is None:
            self.learning_insights = []


class AgentWorkLogSystem:
    """智能體工作日誌系統"""

    TASK_CATEGORIES = {
        "resume": "履歷製作與優化",
        "learning": "對話學習與知識提取",
        "revenue": "收益追蹤與報告",
        "platform": "平台申請與跟進",
        "optimization": "系統優化與改進",
    }

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.work_log_file = self.log_dir / "agent_work_log.json"
        self.daily_summary_dir = self.log_dir / "daily_summaries"
        self.daily_summary_dir.mkdir(parents=True, exist_ok=True)

        self.work_log = self._load_work_log()

    def log_task(
        self,
        task_category: str,
        task_name: str,
        description: str,
        status: str = "completed",
        time_spent: int = 0,
        results: Dict[str, Any] = None,
        insights: List[str] = None,
    ) -> Dict[str, Any]:
        """
        記錄一項工作任務

        Args:
            task_category: 任務類別
            task_name: 任務名稱
            description: 充分描述
            status: 狀態 (completed, in_progress, pending)
            time_spent: 耗時（分鐘）
            results: 結果數據
            insights: 學習要點

        Returns:
            記錄的工作日誌條目
        """
        if task_category not in self.TASK_CATEGORIES:
            raise ValueError(f"Unknown task category: {task_category}")

        entry = WorkLog(
            date=datetime.now().isoformat(),
            task_category=task_category,
            task_name=task_name,
            description=description,
            status=status,
            time_spent_minutes=time_spent,
            results=results or {},
            learning_insights=insights or [],
        )

        self.work_log.append(asdict(entry))
        self._save_work_log()

        return asdict(entry)

    def get_today_summary(self) -> Dict[str, Any]:
        """獲取今日工作摘要"""
        today = datetime.now().strftime("%Y-%m-%d")

        today_logs = [log for log in self.work_log if log["date"].startswith(today)]

        summary = {
            "date": today,
            "total_tasks": len(today_logs),
            "completed_tasks": sum(
                1 for log in today_logs if log["status"] == "completed"
            ),
            "total_time_minutes": sum(log["time_spent_minutes"] for log in today_logs),
            "by_category": {},
            "all_insights": [],
            "key_results": {},
        }

        # 按類別統計
        for log in today_logs:
            category = log["task_category"]
            if category not in summary["by_category"]:
                summary["by_category"][category] = {"count": 0, "tasks": []}
            summary["by_category"][category]["count"] += 1
            summary["by_category"][category]["tasks"].append(log["task_name"])

            # 收集所有學習要點
            summary["all_insights"].extend(log.get("learning_insights", []))

            # 收集關鍵結果
            if log["results"]:
                summary["key_results"][log["task_name"]] = log["results"]

        return summary

    def get_weekly_report(self) -> Dict[str, Any]:
        """生成週報"""
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")

        week_logs = [
            log for log in self.work_log if log["date"].startswith(week_start_str[:7])
        ]  # 簡易週篩選

        report = {
            "week_start": week_start_str,
            "total_tasks": len(week_logs),
            "completed": sum(1 for log in week_logs if log["status"] == "completed"),
            "total_hours": sum(log["time_spent_minutes"] for log in week_logs) / 60,
            "by_category": {},
            "key_achievements": [
                log["task_name"] for log in week_logs if log["status"] == "completed"
            ],
        }

        for category in self.TASK_CATEGORIES:
            logs = [log for log in week_logs if log["task_category"] == category]
            report["by_category"][category] = {
                "count": len(logs),
                "completed": sum(1 for log in logs if log["status"] == "completed"),
            }

        return report

    def export_daily_summary(self) -> str:
        """導出今日工作總結為 Markdown"""
        summary = self.get_today_summary()
        today = datetime.now().strftime("%Y-%m-%d")

        md_content = f"""# 智能體日誌 - {today}

## 📊 每日統計
- **完成任務數**: {summary["completed_tasks"]}/{summary["total_tasks"]}
- **總耗時**: {summary["total_time_minutes"]:.0f} 分鐘 ({summary["total_time_minutes"] / 60:.1f} 小時)

## 📋 按類別統計

"""

        for category, data in summary["by_category"].items():
            cat_name = self.TASK_CATEGORIES.get(category, category)
            md_content += f"""### {cat_name}
- 任務數: {data["count"]}
- 任務: {", ".join(data["tasks"])}

"""

        if summary["all_insights"]:
            md_content += """## 💡 今日學習要點

"""
            for insight in summary["all_insights"]:
                md_content += f"- {insight}\n"

        if summary["key_results"]:
            md_content += """## 🎯 關鍵結果

"""
            for task, result in summary["key_results"].items():
                md_content += f"- {task}: {result}\n"

        # 保存到檔案
        summary_file = self.daily_summary_dir / f"summary_{today}.md"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        return str(summary_file)

    def _load_work_log(self) -> List[Dict[str, Any]]:
        """加載工作日誌"""
        if self.work_log_file.exists():
            with open(self.work_log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_work_log(self):
        """保存工作日誌"""
        with open(self.work_log_file, "w", encoding="utf-8") as f:
            json.dump(self.work_log, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 導入需要的模塊
    from datetime import timedelta

    # 使用示例
    sys = AgentWorkLogSystem()

    print("🤖 智能體工作日誌系統")
    print("=" * 60)

    # 記錄今天的工作
    sys.log_task(
        task_category="resume",
        task_name="完成個人履歷與平台簡歷",
        description="根據用戶信息創建中英雙語履歷，強調精神醫療背景",
        status="completed",
        time_spent=120,
        results={"documents_created": 3, "bilingual_coverage": "100%"},
        insights=[
            "完整的中英雙語對照提高國際競爭力",
            "充分利用獨特背景（精神醫療+社工）作為差異化優勢",
        ],
    )

    sys.log_task(
        task_category="platform",
        task_name="建立平台申請追蹤系統",
        description="創建自動追蹤平台申請狀態的工具",
        status="completed",
        time_spent=90,
        results={"platforms_tracked": 5, "followup_reminders": "enabled"},
        insights=["系統性地追蹤多平台申請進度", "自動提醒跟進時間"],
    )

    sys.log_task(
        task_category="learning",
        task_name="記錄履歷製作對話學習",
        description="自主記錄履歷製作過程的學習內容",
        status="completed",
        time_spent=30,
    )

    # 獲取今日摘要
    print("\n📊 今日工作摘要:")
    summary = sys.get_today_summary()
    print(f"   完成任務: {summary['completed_tasks']}/{summary['total_tasks']}")
    print(f"   總耗時: {summary['total_time_minutes']:.0f} 分鐘")

    # 導出每日總結
    summary_file = sys.export_daily_summary()
    print(f"\n✅ 每日總結已保存: {summary_file}")

    print("\n" + "=" * 60)

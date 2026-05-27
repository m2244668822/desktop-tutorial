#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體接案與收益管理系統 (Agent Task & Revenue Management System)

核心功能：
1. 自動接案系統 (Task Acquisition)
   - 從多個渠道檢測任務機會
   - 評估任務可行性和收益
   - 自動接受符合條件的任務

2. 任務管理系統 (Task Management)
   - 任務優先級調度
   - 進度追蹤
   - 自動完成驗證

3. 收益管理系統 (Revenue Management)
   - 收益計算
   - 成本分析
   - 利潤優化
   - 自動結算

4. 市場分析 (Market Analysis)
   - 中文 AI 模型工作需求分析
   - 價格策略建議
   - 競爭力評估
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import uuid
from enum import Enum


class TaskStatus(Enum):
    """任務狀態"""

    AVAILABLE = "available"  # 可用
    ACCEPTED = "accepted"  # 已接受
    IN_PROGRESS = "in_progress"  # 進行中
    COMPLETED = "completed"  # 已完成
    PAID = "paid"  # 已支付
    RETIRED = "retired"  # 已歸檔


class TaskType(Enum):
    """任務類型"""

    SMALL_PROJECT = "small_project"  # 小項目 (5k-15k)
    CONSULTING = "consulting"  # 諮詢服務 (2k-10k)
    CONTENT_CREATION = "content_creation"  # 內容創建 (1k-5k)
    MODEL_TRAINING = "model_training"  # 模型訓練 (10k-50k)
    DATA_ANNOTATION = "data_annotation"  # 數據標註 (500-5k)
    OPTIMIZATION = "optimization"  # 優化工作 (3k-20k)


class AgentTaskManager:
    """智能體任務管理器"""

    def __init__(
        self, tasks_dir: str = "data/business", revenue_dir: str = "data/revenue"
    ):
        """
        初始化任務管理器

        Args:
            tasks_dir: 任務存儲目錄
            revenue_dir: 收益存儲目錄
        """
        self.tasks_dir = Path(tasks_dir)
        self.revenue_dir = Path(revenue_dir)

        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.revenue_dir.mkdir(parents=True, exist_ok=True)

        # 文件路徑
        self.tasks_file = self.tasks_dir / "tasks.json"
        self.opportunities_file = self.tasks_dir / "opportunities.json"
        self.assignments_file = self.tasks_dir / "assignments.json"
        self.revenue_file = self.revenue_dir / "revenue.json"
        self.invoices_file = self.revenue_dir / "invoices.json"
        self.reports_file = self.revenue_dir / "reports.json"

        # 加載現有數據
        self.tasks = self._load_json(self.tasks_file, default={})
        self.opportunities = self._load_json(self.opportunities_file, default=[])
        self.revenue_records = self._load_json(self.revenue_file, default=[])

        # 配置參數
        self.acceptable_task_min_revenue = 500  # 最小可接受收益 (元)
        self.work_capacity = 100  # 日容量 (百分比)
        self.current_load = 0  # 當前工作負荷

        print(f"✅ 任務管理器已初始化")
        print(f"   已有任務: {len(self.tasks)}")
        print(f"   機會數: {len(self.opportunities)}")

    def create_opportunity(
        self,
        title: str,
        description: str,
        task_type: str,
        estimated_budget: float,
        deadline: Optional[str] = None,
        source: str = "manual",
        requirements: List[str] = None,
    ) -> Dict[str, Any]:
        """
        創建任務機會

        Args:
            title: 機會標題
            description: 詳細描述
            task_type: 任務類型
            estimated_budget: 預計預算
            deadline: 截止日期
            source: 來源
            requirements: 需求列表

        Returns:
            創建的機會記錄
        """
        opportunity = {
            "id": f"opp_{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "description": description,
            "task_type": task_type,
            "estimated_budget": estimated_budget,
            "deadline": deadline,
            "source": source,
            "requirements": requirements or [],
            "priority": self._calculate_opportunity_priority(
                estimated_budget, deadline
            ),
            "feasibility": self._assess_feasibility(task_type, requirements),
            "status": "available",
            "expected_revenue_ratio": 0.7,  # 70% 作為實際收入
            "expected_net_revenue": estimated_budget * 0.7,
        }

        self.opportunities.append(opportunity)
        self._save_json(self.opportunities_file, self.opportunities)

        print(f"✅ 創建機會: {opportunity['id']} - {title}")
        print(f"   預計收益: ¥{opportunity['expected_net_revenue']:.2f}")

        return opportunity

    def evaluate_and_accept_task(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """
        評估並接受任務

        Args:
            opportunity_id: 機會 ID

        Returns:
            接受的任務記錄
        """
        # 尋找機會
        opportunity = None
        for opp in self.opportunities:
            if opp["id"] == opportunity_id:
                opportunity = opp
                break

        if not opportunity:
            print(f"❌ 找不到機會: {opportunity_id}")
            return None

        # 評估能力
        can_accept = self._evaluate_capability(opportunity)

        if not can_accept["can_accept"]:
            print(f"❌ 無法接受任務: {can_accept['reason']}")
            return None

        # 創建任務
        task = {
            "id": f"task_{uuid.uuid4().hex[:8]}",
            "opportunity_id": opportunity_id,
            "title": opportunity["title"],
            "description": opportunity["description"],
            "task_type": opportunity["task_type"],
            "budget": opportunity["estimated_budget"],
            "created_at": datetime.now().isoformat(),
            "deadline": opportunity["deadline"],
            "status": TaskStatus.ACCEPTED.value,
            "estimated_hours": self._estimate_hours(opportunity),
            "estimated_cost": self._estimate_cost(opportunity),
            "assigned_to": "local_model",
            "progress": 0,
            "milestones": self._create_milestones(opportunity),
            "revenue_terms": {
                "currency": "CNY",
                "amount": opportunity["expected_net_revenue"],
                "payment_schedule": "upon_completion",
            },
        }

        self.tasks[task["id"]] = task
        self._save_json(self.tasks_file, self.tasks)

        # 更新工作負荷
        self.current_load += self._calculate_task_load(task)

        print(f"✅ 接受任務: {task['id']}")
        print(f"   預計時數: {task['estimated_hours']} 小時")
        print(f"   預計成本: ¥{task['estimated_cost']:.2f}")
        print(f"   預計收益: ¥{task['revenue_terms']['amount']:.2f}")

        # 更新機會狀態
        opportunity["status"] = "accepted"
        self._save_json(self.opportunities_file, self.opportunities)

        return task

    def update_task_progress(
        self, task_id: str, progress: int, notes: str = ""
    ) -> bool:
        """
        更新任務進度

        Args:
            task_id: 任務 ID
            progress: 進度百分比 (0-100)
            notes: 備註

        Returns:
            是否成功
        """
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]
        old_progress = task.get("progress", 0)
        task["progress"] = min(100, max(0, progress))
        task["last_update"] = datetime.now().isoformat()

        if notes:
            task["notes"] = notes

        # 如果完成，更新狀態
        if progress >= 100:
            task["status"] = TaskStatus.COMPLETED.value
            task["completed_at"] = datetime.now().isoformat()
            print(f"✅ 任務完成: {task_id}")

            # 記錄收益
            self._record_revenue(task)

        self._save_json(self.tasks_file, self.tasks)

        return True

    def _calculate_opportunity_priority(
        self, budget: float, deadline: Optional[str]
    ) -> str:
        """計算機會優先級"""
        priority = "medium"

        if budget > 20000:
            priority = "critical"
        elif budget > 10000:
            priority = "high"
        elif budget < 1000:
            priority = "low"

        # 考慮截止日期
        if deadline:
            try:
                deadline_date = datetime.fromisoformat(deadline)
                days_left = (deadline_date - datetime.now()).days

                if days_left < 3:
                    priority = "critical"
                elif days_left < 7:
                    priority = "high"
            except:
                pass

        return priority

    def _assess_feasibility(self, task_type: str, requirements: List[str]) -> float:
        """評估任務可行性 (0-1)"""
        feasibility = 0.5

        # 基於任務類型
        type_feasibility = {
            "small_project": 0.8,
            "consulting": 0.9,
            "content_creation": 0.95,
            "model_training": 0.7,
            "data_annotation": 0.85,
            "optimization": 0.75,
        }
        feasibility = type_feasibility.get(task_type, 0.5)

        # 基於需求
        favorable_requirements = ["中文", "本地", "離線", "優化", "學習"]

        for req in requirements:
            if any(keyword in req for keyword in favorable_requirements):
                feasibility += 0.05

        return min(feasibility, 1.0)

    def _evaluate_capability(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """評估智能體接納能力"""
        evaluation = {"can_accept": False, "reason": "", "score": 0}

        # 檢查最小收益
        if opportunity["expected_net_revenue"] < self.acceptable_task_min_revenue:
            evaluation["reason"] = "低於最小收益閾值"
            return evaluation

        # 檢查工作容量
        task_load = opportunity["estimated_budget"] / 10000 * 30  # 估計負荷
        if self.current_load + task_load > self.work_capacity:
            evaluation["reason"] = "工作容量不足"
            return evaluation

        # 檢查時間
        if opportunity["deadline"]:
            try:
                deadline = datetime.fromisoformat(opportunity["deadline"])
                if deadline < datetime.now():
                    evaluation["reason"] = "截止日期已過"
                    return evaluation
            except:
                pass

        # 可接納
        evaluation["can_accept"] = True
        evaluation["score"] = opportunity["feasibility"]

        return evaluation

    def _estimate_hours(self, opportunity: Dict[str, Any]) -> int:
        """估計所需時數"""
        task_type = opportunity["task_type"]
        budget = opportunity["estimated_budget"]

        # 基於任務類型和預算估計
        hours_per_thousand = {
            "small_project": 80,
            "consulting": 40,
            "content_creation": 30,
            "model_training": 120,
            "data_annotation": 50,
            "optimization": 60,
        }

        base_hours = hours_per_thousand.get(task_type, 50) * (budget / 1000)

        return int(base_hours)

    def _estimate_cost(self, opportunity: Dict[str, Any]) -> float:
        """估計運營成本"""
        # 基本成本估計：機器成本、電力、人工成本等
        estimated_hours = self._estimate_hours(opportunity)
        hourly_cost = 50  # 每小時運營成本 (元)

        total_cost = estimated_hours * hourly_cost

        return min(total_cost, opportunity["estimated_budget"] * 0.3)  # 不超過預算的30%

    def _calculate_task_load(self, task: Dict[str, Any]) -> float:
        """計算任務的工作負荷"""
        hours = task.get("estimated_hours", 0)
        # 假設日工作8小時，計算百分比
        return (hours / (task.get("deadline") and 8 or 168)) * 100

    def _create_milestones(self, opportunity: Dict[str, Any]) -> List[Dict]:
        """創建項目里程碑"""
        milestones = [
            {"name": "需求確認", "progress": 0, "due_date": None},
            {"name": "設計方案", "progress": 25, "due_date": None},
            {"name": "開發實現", "progress": 50, "due_date": None},
            {"name": "測試驗收", "progress": 75, "due_date": None},
            {"name": "交付部署", "progress": 100, "due_date": opportunity["deadline"]},
        ]

        return milestones

    def _record_revenue(self, task: Dict[str, Any]):
        """記錄收益"""
        revenue_record = {
            "id": f"rev_{uuid.uuid4().hex[:8]}",
            "task_id": task["id"],
            "title": task["title"],
            "amount": task["revenue_terms"]["amount"],
            "cost": task["estimated_cost"],
            "net_profit": task["revenue_terms"]["amount"] - task["estimated_cost"],
            "recorded_at": datetime.now().isoformat(),
            "paid": False,
        }

        self.revenue_records.append(revenue_record)
        self._save_json(self.revenue_file, self.revenue_records)

        # 更新工作負荷
        self.current_load -= self._calculate_task_load(task)

    def generate_revenue_report(self, period_days: int = 30) -> Dict[str, Any]:
        """生成收益報告"""
        cutoff_date = datetime.now() - timedelta(days=period_days)

        period_records = [
            r
            for r in self.revenue_records
            if datetime.fromisoformat(r["recorded_at"]) >= cutoff_date
        ]

        report = {
            "period": f"最近 {period_days} 天",
            "report_date": datetime.now().isoformat(),
            "total_revenue": sum(r["amount"] for r in period_records),
            "total_cost": sum(r["cost"] for r in period_records),
            "total_profit": sum(r["net_profit"] for r in period_records),
            "task_count": len(period_records),
            "average_profit_per_task": (
                sum(r["net_profit"] for r in period_records) / len(period_records)
                if period_records
                else 0
            ),
            "profit_margin": (
                sum(r["net_profit"] for r in period_records)
                / sum(r["amount"] for r in period_records)
                * 100
                if period_records
                else 0
            ),
            "records": period_records,
        }

        # 保存報告
        self._save_json(self.reports_file, report)

        return report

    def _load_json(self, path: Path, default: Any = None) -> Any:
        """安全加載 JSON"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default or {}

    def _save_json(self, path: Path, data: Any):
        """安全保存 JSON"""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存失敗: {e}")

    def get_dashboard(self) -> Dict[str, Any]:
        """獲取儀表板信息"""
        return {
            "timestamp": datetime.now().isoformat(),
            "active_tasks": len(
                [
                    t
                    for t in self.tasks.values()
                    if t["status"] not in ["completed", "paid"]
                ]
            ),
            "completed_tasks": len(
                [t for t in self.tasks.values() if t["status"] == "completed"]
            ),
            "available_opportunities": len(
                [o for o in self.opportunities if o["status"] == "available"]
            ),
            "current_workload": f"{self.current_load:.1f}%",
            "total_revenue": sum(r["amount"] for r in self.revenue_records),
            "total_profit": sum(r["net_profit"] for r in self.revenue_records),
            "recent_revenue": sum(
                r["net_profit"]
                for r in self.revenue_records
                if datetime.fromisoformat(r["recorded_at"])
                > datetime.now() - timedelta(days=7)
            ),
        }


if __name__ == "__main__":
    # 使用示例
    manager = AgentTaskManager()

    # 創建機會
    opportunity = manager.create_opportunity(
        title="中文 AI 模型優化項目",
        description="優化本地中文 AI 模型的推理性能",
        task_type="model_training",
        estimated_budget=15000,
        deadline="2026-04-01",
        requirements=["中文優化", "本地模型", "性能改進"],
    )

    # 接受任務
    task = manager.evaluate_and_accept_task(opportunity["id"])

    if task:
        # 更新進度
        for progress in [25, 50, 75, 100]:
            manager.update_task_progress(task["id"], progress, f"完成進度 {progress}%")

    # 生成報告
    report = manager.generate_revenue_report()
    print("\n💰 收益報告:")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 獲取儀表板
    dashboard = manager.get_dashboard()
    print("\n📊 儀表板:")
    print(json.dumps(dashboard, ensure_ascii=False, indent=2))

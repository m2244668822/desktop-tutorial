#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體協調管理器
協調所有智能體之間的協作
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Dict
import threading

BASE_DIR = Path(__file__).resolve().parent


class AgentCoordinator:
    """智能體協調管理器"""

    AGENT_TYPES = {
        "總管": {"role": "協調", "priority": 1},
        "研究員": {"role": "研究", "priority": 2},
        "工程師": {"role": "執行", "priority": 3},
        "中繼器": {"role": "橋接", "priority": 4},
        "帽子": {"role": "安全", "priority": 5},
    }

    def __init__(self):
        self.base_dir = BASE_DIR
        self.agents = {}
        self.tasks = []
        self.task_lock = threading.Lock()
        self.coordination_log = self.base_dir / "logs" / "coordination.log"
        self._load_agents()

    def _load_agents(self) -> None:
        """加載智能體"""
        self.agents = {
            "總管": {"status": "active", "tasks_completed": 0},
            "研究員": {"status": "active", "tasks_completed": 0},
            "工程師": {"status": "active", "tasks_completed": 0},
            "中繼器": {"status": "active", "tasks_completed": 0},
            "帽子": {"status": "available", "tasks_completed": 0},
        }
        print(f"已加載 {len(self.agents)} 個智能體")

    def assign_task(self, task: Dict) -> str:
        """分配任務"""
        task_id = f"task_{int(time.time() * 1000)}"

        with self.task_lock:
            agent_type = self._select_agent(task)

            task_entry = {
                "id": task_id,
                "type": task.get("type", "general"),
                "agent": agent_type,
                "status": "assigned",
                "created_at": datetime.now().isoformat(),
                "data": task,
            }

            self.tasks.append(task_entry)
            self.agents[agent_type]["tasks_completed"] += 1

        print(f"任務 {task_id} 已分配給 {agent_type}")
        return task_id

    def _select_agent(self, task: Dict) -> str:
        """選擇合適的智能體"""
        task_type = task.get("type", "").lower()

        type_mapping = {
            "研究": "研究員",
            "分析": "研究員",
            "開發": "工程師",
            "修復": "工程師",
            "安全": "帽子",
            "漏洞": "帽子",
            "掃描": "帽子",
            "協調": "中繼器",
            "管理": "總管",
        }

        for keyword, agent in type_mapping.items():
            if keyword in task_type and agent in self.agents:
                return agent

        return "總管"

    def get_system_status(self) -> Dict:
        """獲取系統狀態"""
        return {
            "total_agents": len(self.agents),
            "active_agents": len(
                [a for a in self.agents.values() if a["status"] == "active"]
            ),
            "total_tasks": len(self.tasks),
            "agents": self.agents,
        }

    def generate_report(self) -> str:
        """生成協調報告"""
        status = self.get_system_status()

        report = ["智能體協調報告", "=" * 30]
        report.append(f"智能體數: {status['total_agents']}")
        report.append(f"活躍智能體: {status['active_agents']}")
        report.append(f"總任務數: {status['total_tasks']}")

        return "\n".join(report)


if __name__ == "__main__":
    coordinator = AgentCoordinator()
    task_id = coordinator.assign_task({"type": "安全分析", "data": {}})
    print(coordinator.generate_report())

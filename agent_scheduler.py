#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體定時任務調度系統
"""

import time
import threading
from datetime import datetime
from typing import Callable, List
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class AgentScheduler:
    """智能體定時任務調度器"""

    def __init__(self):
        self.tasks = {}
        self.running = False
        self.thread = None
        self.log_path = BASE_DIR / "logs" / "scheduler.log"

    def schedule(
        self, task_id: str, interval: int, callback: Callable, args: List = None
    ) -> None:
        """安排定時任務"""
        self.tasks[task_id] = {
            "interval": interval,
            "callback": callback,
            "args": args or [],
            "last_run": 0,
            "enabled": True,
        }
        print(f"任務 {task_id} 已安排，間隔 {interval} 秒")

    def start(self) -> None:
        """啟動調度器"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run)
            self.thread.daemon = True
            self.thread.start()
            print("調度器已啟動")

    def stop(self) -> None:
        """停止調度器"""
        self.running = False
        if self.thread:
            self.thread.join()
        print("調度器已停止")

    def _run(self) -> None:
        """運行調度器"""
        while self.running:
            now = time.time()

            for task_id, task in self.tasks.items():
                if not task["enabled"]:
                    continue

                if now - task["last_run"] >= task["interval"]:
                    try:
                        task["callback"](*task["args"])
                        task["last_run"] = now
                    except Exception as e:
                        print(f"任務 {task_id} 執行失敗: {e}")

            time.sleep(1)


if __name__ == "__main__":
    scheduler = AgentScheduler()

    def sample_task():
        print(f"執行任務: {datetime.now()}")

    scheduler.schedule("sample", 10, sample_task)
    scheduler.start()
    time.sleep(30)
    scheduler.stop()

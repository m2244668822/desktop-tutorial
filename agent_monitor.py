#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體監控系統
"""

import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent


class AgentMonitor:
    """智能體監控器"""

    def __init__(self):
        self.metrics: Dict[str, List] = {
            "cpu": [],
            "memory": [],
            "disk": [],
            "network": [],
        }
        self.monitoring = False
        self.thread = None
        self.log_path = BASE_DIR / "logs" / "monitor.log"

    def start_monitoring(self, interval: int = 60) -> None:
        """開始監控"""
        self.monitoring = True
        self.thread = threading.Thread(target=self._monitor, args=(interval,))
        self.thread.daemon = True
        self.thread.start()
        print("監控已啟動")

    def stop_monitoring(self) -> None:
        """停止監控"""
        self.monitoring = False
        if self.thread:
            self.thread.join()
        print("監控已停止")

    def _monitor(self, interval: int) -> None:
        """監控循環"""
        try:
            import psutil
        except ImportError:
            print("psutil 未安裝，跳過系統監控")
            return

        while self.monitoring:
            try:
                cpu = psutil.cpu_percent(interval=1)
                self.metrics["cpu"].append(
                    {"time": datetime.now().isoformat(), "value": cpu}
                )

                mem = psutil.virtual_memory()
                self.metrics["memory"].append(
                    {
                        "time": datetime.now().isoformat(),
                        "percent": mem.percent,
                        "used_mb": mem.used / (1024 * 1024),
                    }
                )

                disk = psutil.disk_usage("/")
                self.metrics["disk"].append(
                    {"time": datetime.now().isoformat(), "percent": disk.percent}
                )

                for key in self.metrics:
                    if len(self.metrics[key]) > 100:
                        self.metrics[key] = self.metrics[key][-100:]

            except Exception as e:
                print(f"監控錯誤: {e}")

            time.sleep(interval)

    def get_current_stats(self) -> dict:
        """獲取當前統計"""
        stats = {}

        if self.metrics["cpu"]:
            stats["cpu"] = self.metrics["cpu"][-1]["value"]

        if self.metrics["memory"]:
            stats["memory"] = self.metrics["memory"][-1]["percent"]

        return stats


if __name__ == "__main__":
    monitor = AgentMonitor()
    monitor.start_monitoring(10)

    try:
        time.sleep(15)
    except KeyboardInterrupt:
        pass

    monitor.stop_monitoring()
    print("當前統計:", monitor.get_current_stats())

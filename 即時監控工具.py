#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即時系統監控工具
"""

import os
import sys
import time
import psutil
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
import json

BASE_DIR = Path(__file__).resolve().parent


class RealTimeMonitor:
    """即時系統監控器"""

    def __init__(self):
        self.base_dir = BASE_DIR
        self.monitor_log = self.base_dir / "logs" / "realtime_monitor.log"
        self.monitor_log.parent.mkdir(parents=True, exist_ok=True)

        # 監控配置
        self.config = {
            "file_monitoring": True,
            "process_monitoring": True,
            "resource_monitoring": True,
            "interval": 5,  # 秒
        }

        # 檔案哈希緩存
        self.file_hashes: Dict[str, str] = {}

        # 初始掃描
        self._initial_scan()

        # 警報歷史
        self.alerts: List[Dict] = []

        # 運行了
        self.running = False

    def _initial_scan(self) -> None:
        """初始掃描"""
        print("執行初始檔案掃描...")

        # 掃描 Python 檔案
        for f in self.base_dir.rglob("*.py"):
            try:
                self.file_hashes[str(f)] = self._compute_hash(f)
            except Exception:
                pass

        print(f"初始掃描完成，共 {len(self.file_hashes)} 個檔案")

    def _compute_hash(self, filepath: Path) -> str:
        """計算檔案哈希"""
        try:
            with open(filepath, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def log(self, message: str, level: str = "INFO") -> None:
        """記錄日誌"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"

        try:
            with open(self.monitor_log, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception:
            pass

    def check_file_changes(self) -> List[Dict]:
        """檢查檔案變更"""
        changes = []

        # 檢查新增和修改的檔案
        for f in self.base_dir.rglob("*.py"):
            try:
                filepath = str(f)
                new_hash = self._compute_hash(f)
                old_hash = self.file_hashes.get(filepath)

                if old_hash is None:
                    changes.append(
                        {
                            "type": "新增",
                            "file": f.name,
                            "path": filepath,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    self.file_hashes[filepath] = new_hash

                elif new_hash != old_hash:
                    changes.append(
                        {
                            "type": "修改",
                            "file": f.name,
                            "path": filepath,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    self.file_hashes[filepath] = new_hash

            except Exception:
                pass

        # 檢查刪除的檔案（通過記錄數量減少）
        current_count = len(self.file_hashes)

        return changes

    def check_processes(self) -> Dict:
        """檢查程序運行狀態"""
        info = {
            "timestamp": datetime.now().isoformat(),
            "total_processes": 0,
            "python_processes": [],
            "suspicious": [],
        }

        # 系統程序
        info["total_processes"] = len(psutil.pids())

        # Python 程序
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "create_time"]
        ):
            try:
                name = proc.info["name"]
                if "python" in name.lower():
                    info["python_processes"].append(
                        {
                            "pid": proc.info["pid"],
                            "name": name,
                            "cpu": proc.info["cpu_percent"],
                            "memory": proc.info["memory_percent"],
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return info

    def check_resources(self) -> Dict:
        """檢查系統資源"""
        resources = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory": {
                "percent": psutil.virtual_memory().percent,
                "used_gb": psutil.virtual_memory().used / (1024**3),
                "available_gb": psutil.virtual_memory().available / (1024**3),
            },
            "disk": {
                "percent": psutil.disk_usage("/").percent,
                "free_gb": psutil.disk_usage("/").free / (1024**3),
            },
        }

        # 警報條件
        if resources["cpu_percent"] > 80:
            self.alerts.append(
                {
                    "level": "warning",
                    "message": f"CPU 使用率過高: {resources['cpu_percent']:.1f}%",
                    "timestamp": resources["timestamp"],
                }
            )

        if resources["memory"]["percent"] > 85:
            self.alerts.append(
                {
                    "level": "warning",
                    "message": f"記憶體使用率過高: {resources['memory']['percent']:.1f}%",
                    "timestamp": resources["timestamp"],
                }
            )

        return resources

    def monitor_loop(self) -> None:
        """監控循環"""
        print("\n" + "=" * 60)
        print("即時系統監控 - 執行中")
        print("=" * 60)
        print(f"監控目錄: {self.base_dir}")
        print(f"監控間隔: {self.config['interval']} 秒")
        print("-" * 60)

        iteration = 0

        while self.running:
            iteration += 1
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 檢查 #{iteration}")

            # 1. 檔案變更檢查
            if self.config["file_monitoring"]:
                changes = self.check_file_changes()
                if changes:
                    print("📝 偵測到檔案變更:")
                    for change in changes:
                        print(f"   {change['type']}: {change['file']}")
                        self.log(
                            f"檔案變更: {change['type']} {change['file']}", "WARNING"
                        )
                else:
                    print("✅ 檔案無變更")

            # 2. 程序檢查
            if self.config["process_monitoring"]:
                proc_info = self.check_processes()
                python_count = len(proc_info["python_processes"])
                print(f"🐍 Python 程序數: {python_count}")

                if python_count > 10:
                    print(f"   ⚠️ 程序數量較多")

            # 3. 資源檢查
            if self.config["resource_monitoring"]:
                resources = self.check_resources()
                cpu = resources["cpu_percent"]
                mem = resources["memory"]["percent"]
                disk = resources["disk"]["percent"]

                print(
                    f"💻 CPU: {cpu:.1f}% | 🧠 記憶體: {mem:.1f}% | 💾 硬碟: {disk:.1f}%"
                )

                # 警報顯示
                if self.alerts:
                    print("\n⚠️ 警報:")
                    for alert in self.alerts[-3:]:
                        print(f"   [{alert['level']}] {alert['message']}")

            # 等待
            time.sleep(self.config["interval"])

    def start(self) -> None:
        """啟動監控"""
        self.running = True
        self.monitor_loop()

    def stop(self) -> None:
        """停止監控"""
        self.running = False
        print("\n監控已停止")


def quick_status() -> None:
    """快速狀態檢查"""
    print("\n" + "=" * 50)
    print("系統快速狀態檢查")
    print("=" * 50)

    # CPU
    cpu = psutil.cpu_percent(interval=1)
    print(f"\n💻 CPU: {cpu:.1f}%")

    # 記憶體
    mem = psutil.virtual_memory()
    print(
        f"🧠 記憶體: {mem.percent:.1f}% ({mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB)"
    )

    # 硬碟
    disk = psutil.disk_usage("/")
    print(f"💾 硬碟: {disk.percent:.1f}% ({disk.free / (1024**3):.1f}GB 可用)")

    # 網路
    net = psutil.net_io_counters()
    print(
        f"🌐 網路: 發送 {net.bytes_sent / (1024**2):.1f}MB | 接收 {net.bytes_recv / (1024**2):.1f}MB"
    )

    # 程序
    print(f"\n🐍 Python 程序:")
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            if "python" in proc.info["name"].lower():
                print(
                    f"   PID {proc.info['pid']}: {proc.info['name']} (CPU: {proc.info['cpu_percent']:.1f}%, MEM: {proc.info['memory_percent']:.1f}%)"
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print("\n" + "=" * 50)


def monitor_files() -> None:
    """專門監控檔案變更"""
    monitor = RealTimeMonitor()
    monitor.config["process_monitoring"] = False
    monitor.config["resource_monitoring"] = False
    monitor.start()


def monitor_resources() -> None:
    """專門監控資源"""
    monitor = RealTimeMonitor()
    monitor.config["file_monitoring"] = False
    monitor.config["process_monitoring"] = False

    iteration = 0
    while True:
        iteration += 1
        resources = monitor.check_resources()

        cpu = resources["cpu_percent"]
        mem = resources["memory"]["percent"]
        disk = resources["disk"]["percent"]

        status = "✅"
        if cpu > 80 or mem > 85:
            status = "⚠️"
        if cpu > 95 or mem > 95:
            status = "🔴"

        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {status} CPU: {cpu:.1f}% | MEM: {mem:.1f}% | DISK: {disk:.1f}%"
        )

        time.sleep(2)


def main():
    """主函數"""
    if len(sys.argv) < 2:
        print("""
即時系統監控工具
================

用法:
    python3 即時監控工具.py [選項]

選項:
    status     - 快速狀態檢查
    files      - 監控檔案變更
    resources  - 監控系統資源
    all        - 完整監控 (預設)

範例:
    python3 即時監控工具.py status
    python3 即時監控工具.py files
        """)

        # 預設執行完整監控
        sys.argv.append("all")

    command = sys.argv[1].lower()

    if command == "status":
        quick_status()
    elif command == "files":
        monitor_files()
    elif command == "resources":
        monitor_resources()
    else:
        monitor = RealTimeMonitor()
        try:
            monitor.start()
        except KeyboardInterrupt:
            monitor.stop()


if __name__ == "__main__":
    main()

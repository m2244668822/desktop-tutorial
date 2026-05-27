#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自主監控和異常通報系統
- 監控中樞神經和智能體的運作狀態
- 發現異常時即時通報
- 促進兩者自主決策和協作
"""

import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict


class AutonomousMonitor:
    """自主監控系統 - 監視和通報系統異常"""

    def __init__(self, checkpoint_interval: int = 5):
        self.checkpoint_interval = checkpoint_interval  # 檢查間隔 (秒)
        self.monitoring = False
        self.monitor_thread = None

        # 監控的系統
        self.neural_anomalies_file = Path("neural_anomalies.json")
        self.agent_anomalies_file = Path("agent_anomalies.json")
        self.system_health_file = Path("data/system_health.json")

        # 狀態追蹤
        self.last_checked = {"neural": None, "agent": None, "system": None}

        # 通知日誌
        self.notifications = []

        # 自主決策記錄
        self.autonomous_actions = []

    def start(self):
        """啟動監控"""
        if self.monitoring:
            print("❌ 監控已在運行")
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("✅ 自主監控已啟動")

    def stop(self):
        """停止監控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("⏹️ 自主監控已停止")

    def _monitor_loop(self):
        """持續監控迴圈"""
        while self.monitoring:
            try:
                self._check_neural_anomalies()
                self._check_agent_anomalies()
                self._check_system_health()
                time.sleep(self.checkpoint_interval)
            except Exception as e:
                self._report_critical_error(f"監控迴圈錯誤: {e}")

    def _check_neural_anomalies(self):
        """檢查神經系統異常"""
        if not self.neural_anomalies_file.exists():
            return

        try:
            with open(self.neural_anomalies_file, "r") as f:
                data = json.load(f)

            last_update = data.get("last_updated")
            if last_update != self.last_checked["neural"]:
                anomalies = data.get("anomalies", [])
                if anomalies:
                    latest = anomalies[-1]
                    self._process_neural_anomaly(latest)
                    self.last_checked["neural"] = last_update

        except Exception as e:
            print(f"❌ 讀取神經異常失敗: {e}")

    def _check_agent_anomalies(self):
        """檢查智能體異常"""
        if not self.agent_anomalies_file.exists():
            return

        try:
            with open(self.agent_anomalies_file, "r") as f:
                data = json.load(f)

            last_update = data.get("last_updated")
            if last_update != self.last_checked["agent"]:
                anomalies = data.get("anomalies", [])
                if anomalies:
                    latest = anomalies[-1]
                    self._process_agent_anomaly(latest)
                    self.last_checked["agent"] = last_update

        except Exception as e:
            print(f"❌ 讀取智能體異常失敗: {e}")

    def _check_system_health(self):
        """檢查整體系統健康度"""
        if not self.system_health_file.exists():
            return

        try:
            with open(self.system_health_file, "r") as f:
                health = json.load(f)

            # 檢查關鍵指標
            cpu_usage = health.get("cpu_usage", 0)
            memory_usage = health.get("memory_usage", 0)
            response_time = health.get("avg_response_time_ms", 0)

            issues = []
            if cpu_usage > 80:
                issues.append(f"CPU 過高: {cpu_usage}%")
            if memory_usage > 85:
                issues.append(f"記憶體過高: {memory_usage}%")
            if response_time > 1000:
                issues.append(f"響應時間過長: {response_time}ms")

            if issues:
                self._report_system_warning(issues)

        except Exception as e:
            pass  # 系統健康文件可能不存在

    def _process_neural_anomaly(self, anomaly: Dict):
        """處理神經系統異常"""
        severity = anomaly.get("severity", "info")
        anom_type = anomaly.get("type", "unknown")
        details = anomaly.get("details", {})

        notification = {
            "timestamp": datetime.now().isoformat(),
            "source": "神經中樞",
            "type": anom_type,
            "severity": severity,
            "message": f"神經系統檢測到 {anom_type}: {details}",
        }

        self._notify(notification)

        # 根據嚴重性採取自主行動
        if severity == "critical":
            self._autonomous_action_critical_neural(anom_type, details)

    def _process_agent_anomaly(self, anomaly: Dict):
        """處理智能體異常"""
        severity = anomaly.get("severity", "info")
        anom_type = anomaly.get("type", "unknown")
        agent_id = anomaly.get("agent_id", "unknown")

        notification = {
            "timestamp": datetime.now().isoformat(),
            "source": f"智能體 {agent_id}",
            "type": anom_type,
            "severity": severity,
            "message": f"智能體 {agent_id} 檢測到異常: {anom_type}",
        }

        self._notify(notification)

        # 根據嚴重性採取自主行動
        if severity == "critical":
            self._autonomous_action_critical_agent(agent_id, anom_type)

    def _report_system_warning(self, issues: List[str]):
        """報告系統警告"""
        notification = {
            "timestamp": datetime.now().isoformat(),
            "source": "系統監控",
            "type": "system_health_warning",
            "severity": "warning",
            "message": f"系統警告: {', '.join(issues)}",
        }

        self._notify(notification)

    def _report_critical_error(self, message: str):
        """報告臨界錯誤"""
        notification = {
            "timestamp": datetime.now().isoformat(),
            "source": "監控系統",
            "type": "critical_error",
            "severity": "critical",
            "message": message,
        }

        self._notify(notification)

    def _notify(self, notification: Dict):
        """發送通知"""
        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}

        severity_icon = icon.get(notification["severity"], "⚪")
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"\n{severity_icon} [自主通報] {timestamp} | {notification['source']}")
        print(f"   主題: {notification['type']}")
        print(f"   詳情: {notification['message']}")

        self.notifications.append(notification)

    def _autonomous_action_critical_neural(self, anom_type: str, details: Dict):
        """對神經系統臨界異常的自主行動"""
        action = None

        if anom_type == "low_confidence_query":
            # 自主降低敏感度閾值
            action = {
                "timestamp": datetime.now().isoformat(),
                "type": "自動調整敏感度",
                "source": "神經系統",
                "description": f"偵測低置信度查詢，已調整析敏感度參數",
                "details": details,
            }

        if action:
            self.autonomous_actions.append(action)
            print(f"   ✅ 自主行動: {action['description']}")

    def _autonomous_action_critical_agent(self, agent_id: str, anom_type: str):
        """對智能體臨界異常的自主行動"""
        action = None

        if anom_type == "task_failure":
            # 自主轉移任務給備用智能體
            action = {
                "timestamp": datetime.now().isoformat(),
                "type": "自動轉移任務",
                "source": "監控系統",
                "description": f"智能體 {agent_id} 任務失敗，已轉移給備用智能體",
                "failed_agent": agent_id,
            }
        elif anom_type == "unresponsive":
            # 自主重啟智能體
            action = {
                "timestamp": datetime.now().isoformat(),
                "type": "自動重啟",
                "source": "監控系統",
                "description": f"智能體 {agent_id} 無響應，已觸發重啟",
                "target_agent": agent_id,
            }

        if action:
            self.autonomous_actions.append(action)
            print(f"   ✅ 自主行動: {action['description']}")

    def get_notification_summary(self) -> Dict:
        """獲取通知摘要"""
        by_severity = defaultdict(int)
        by_source = defaultdict(int)

        for notif in self.notifications:
            by_severity[notif["severity"]] += 1
            by_source[notif["source"]] += 1

        return {
            "total_notifications": len(self.notifications),
            "by_severity": dict(by_severity),
            "by_source": dict(by_source),
            "autonomous_actions": len(self.autonomous_actions),
            "latest_notification": self.notifications[-1]
            if self.notifications
            else None,
        }

    def export_logs(self, filename: str = "monitor_logs.json"):
        """匯出監控日誌"""
        data = {
            "export_time": datetime.now().isoformat(),
            "notifications": self.notifications,
            "autonomous_actions": self.autonomous_actions,
            "summary": self.get_notification_summary(),
        }

        with open(filename, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 日誌已匯出到 {filename}")
        return filename


def main():
    """演示自主監控系統"""
    print("=" * 70)
    print("🤖 自主監控和異常通報系統")
    print("=" * 70)

    monitor = AutonomousMonitor(checkpoint_interval=3)
    monitor.start()

    print("\n📊 自主監控已啟動，監聽異常和系統事件...")
    print("   (按 Ctrl+C 停止)\n")

    try:
        while True:
            time.sleep(10)
            summary = monitor.get_notification_summary()
            if summary["total_notifications"] > 0:
                print(f"\n📈 監控摘要:")
                print(f"   - 總通知數: {summary['total_notifications']}")
                print(f"   - 自主行動數: {summary['autonomous_actions']}")

    except KeyboardInterrupt:
        print("\n⏹️ 停止監控...")
        monitor.stop()
        monitor.export_logs()
        print("✅ 監控已停止")


if __name__ == "__main__":
    main()

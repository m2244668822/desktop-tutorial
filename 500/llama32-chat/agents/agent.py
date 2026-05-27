import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加父目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.task_manager import task_manager
from core.constants import *
from core.utils import JsonStorage, TimeHelper, FileHelper


class Agent:
    """智能體 - 管理對話資料、監控請求、記錄失敗"""

    def __init__(self):
        # 確保目錄存在
        FileHelper.ensure_dirs(DATA_DIR, LOGS_DIR)

        self.conversations = JsonStorage.load(CONVERSATION_FILE, default=[])
        self.error_count = 0
        self.success_count = 0
        self.is_running = True

        # 異常報告系統
        self.anomalies_file = Path("agent_anomalies.json")
        self.anomaly_log = []

    def save_conversation(self, model, prompt, response):
        """保存成功的對話"""
        conversation = {
            "timestamp": TimeHelper.now_iso(),
            "model": model,
            "prompt": prompt,
            "response": response,
            "status": "success",
        }
        self.conversations.append(conversation)
        JsonStorage.save(CONVERSATION_FILE, self.conversations)
        self.success_count += 1
        return True

    def log_error(self, model, prompt, error_type, error_message):
        """記錄失敗到文件並通知用戶"""
        error_log = {
            "timestamp": TimeHelper.now_iso(),
            "model": model,
            "prompt": prompt,
            "error_type": error_type,
            "error_message": error_message,
        }

        # 使用 JsonStorage.append 追加日誌記錄
        JsonStorage.append(ERROR_LOG_FILE, error_log)

        self.error_count += 1

        # 立即通知用戶
        self._notify_error(error_log)

        # 報告異常
        self.report_anomaly(
            "task_error",
            {
                "model": model,
                "error_type": error_type,
                "prompt": prompt[:100],
                "error_message": error_message[:200],
            },
            "warning",
        )

        return False

    def report_anomaly(self, anomaly_type: str, details: dict, severity: str = "info"):
        """報告異常事件"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": "main_agent",
            "type": anomaly_type,
            "severity": severity,
            "details": details,
        }

        self.anomaly_log.append(report)
        self._save_anomaly(report)
        self._display_anomaly_alert(report)

    def _save_anomaly(self, report: dict):
        """保存異常到文件"""
        if self.anomalies_file.exists():
            with open(self.anomalies_file, "r") as f:
                data = json.load(f)
        else:
            data = {"anomalies": [], "last_updated": None}

        data["anomalies"].append(report)
        data["last_updated"] = datetime.now().isoformat()

        with open(self.anomalies_file, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _display_anomaly_alert(self, report: dict):
        """顯示異常警報"""
        severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}

        icon = severity_icon.get(report["severity"], "⚪")
        timestamp = report["timestamp"]

        print(f"\n{icon} [智能體異常通報] {timestamp}")
        print(f"   類型: {report['type']}")
        print(f"   嚴重性: {report['severity']}")
        print(f"   詳情: {report['details']}\n")

    def _notify_error(self, error_log):
        """向用戶通知失敗"""
        timestamp = error_log["timestamp"]
        model = error_log["model"]
        error_type = error_log["error_type"]
        error_msg = error_log["error_message"]

        # 在控制台顯示警報
        print("\n" + SEPARATOR_LINE, file=sys.stderr)
        print("❌ 【智能體警報】", file=sys.stderr)
        print(f"時間: {timestamp}", file=sys.stderr)
        print(f"模型: {model}", file=sys.stderr)
        print(f"失敗類型: {error_type}", file=sys.stderr)
        print(f"錯誤信息: {error_msg}", file=sys.stderr)
        print(SEPARATOR_LINE + "\n", file=sys.stderr)

    def get_status(self):
        """獲取智能體狀態"""
        return {
            "status": "running" if self.is_running else "stopped",
            "total_conversations": len(self.conversations),
            "success_count": self.success_count,
            "error_count": self.error_count,
            "conversation_file": str(CONVERSATION_FILE),
            "error_log_file": str(ERROR_LOG_FILE),
        }

    def get_recent_errors(self, limit=10):
        """獲取最近的錯誤記錄"""
        if not ERROR_LOG_FILE.exists():
            return []

        errors = []
        with open(ERROR_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    errors.append(json.loads(line))
                except:
                    pass

        return errors[-limit:]

    def shutdown(self):
        """關閉智能體"""
        self.is_running = False
        JsonStorage.save(CONVERSATION_FILE, self.conversations)
        task_manager.shutdown()
        print("\n✓ 智能體已安全關閉，數據已保存")


# 全局智能體實例
agent = Agent()

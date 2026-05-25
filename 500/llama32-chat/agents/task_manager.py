import uuid
import sys
from pathlib import Path

# 添加父目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import *
from core.utils import JsonStorage, TimeHelper, FileHelper, PrintHelper, StringHelper


class TaskManager:
    """任務管理系統 - 自動檢測、執行、追蹤、記憶"""

    def __init__(self):
        # 確保目錄存在
        FileHelper.ensure_dir(TASKS_DIR)

        self.tasks = JsonStorage.load(TASKS_FILE, default=[])
        self.history = JsonStorage.load(TASK_HISTORY_FILE, default=[])

    def add_task(self, title, description, model, prompt, priority=1, max_retries=3):
        """添加新任務"""
        task = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "description": description,
            "model": model,
            "prompt": prompt,
            "priority": priority,  # 1=高, 2=中, 3=低
            "status": "pending",  # pending, in_progress, completed, failed
            "retry_count": 0,
            "max_retries": max_retries,
            "created_at": TimeHelper.now_iso(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
        }
        self.tasks.append(task)
        JsonStorage.save(TASKS_FILE, self.tasks)

        # 向用戶反饋
        PrintHelper.header("新任務已添加", width=60)
        print(f"ID: {task['id']}")
        print(f"題目: {title}")
        print(f"優先級: {PRIORITY_LEVELS.get(priority, '未知')}")
        PrintHelper.footer()

        return task["id"]

    def get_next_task(self):
        """獲取下一個待執行任務（按優先級排序）"""
        pending = [t for t in self.tasks if t["status"] == "pending"]
        if not pending:
            return None
        # 按優先級排序（優先級數字小的優先）
        return sorted(pending, key=lambda x: x["priority"])[0]

    def start_task(self, task_id):
        """開始執行任務"""
        task = self._find_task(task_id)
        if not task:
            return False

        task["status"] = "in_progress"
        task["started_at"] = TimeHelper.now_iso()
        JsonStorage.save(TASKS_FILE, self.tasks)

        PrintHelper.header("任務開始")
        print(f"ID: {task['id']}")
        print(f"題目: {task['title']}")
        print(f"模型: {task['model']}")
        print(f"提示: {StringHelper.truncate(task['prompt'], TRUNCATE_LENGTH)}")
        PrintHelper.footer()

        return True

    def complete_task(self, task_id, result):
        """完成任務"""
        task = self._find_task(task_id)
        if not task:
            return False

        task["status"] = "completed"
        task["completed_at"] = TimeHelper.now_iso()
        task["result"] = result
        JsonStorage.save(TASKS_FILE, self.tasks)

        # 移到歷史記錄
        self.history.append(task.copy())
        JsonStorage.save(TASK_HISTORY_FILE, self.history)

        duration = TimeHelper.duration(task["started_at"], task["completed_at"])
        PrintHelper.header("任務完成")
        print(f"ID: {task['id']}")
        print(f"題目: {task['title']}")
        print(f"耗時: {duration}")
        PrintHelper.footer()

        return True

    def fail_task(self, task_id, error_msg):
        """標記任務失敗"""
        task = self._find_task(task_id)
        if not task:
            return False

        task["retry_count"] += 1
        task["error"] = error_msg

        if task["retry_count"] >= task["max_retries"]:
            task["status"] = "failed"
            PrintHelper.header("任務失敗", width=60)
            print(f"ID: {task['id']}")
            print(f"題目: {task['title']}")
            print(f"錯誤: {StringHelper.truncate(error_msg, 100)}")
            print(f"重試: {task['retry_count']}/{task['max_retries']}")
            PrintHelper.footer()

            # 移到歷史記錄
            self.history.append(task.copy())
        else:
            task["status"] = "pending"  # 重設為待處理以供重試
            PrintHelper.header("任務失敗 - 準備重試", width=60)
            print(f"ID: {task['id']}")
            print(f"題目: {task['title']}")
            print(f"錯誤: {StringHelper.truncate(error_msg, 100)}")
            print(f"重試: {task['retry_count']}/{task['max_retries']}")
            PrintHelper.footer()

        JsonStorage.save(TASKS_FILE, self.tasks)
        JsonStorage.save(TASK_HISTORY_FILE, self.history)

        return True

    def get_all_pending_tasks(self):
        """獲取所有待處理任務"""
        return [t for t in self.tasks if t["status"] == "pending"]

    def get_status_summary(self):
        """獲取任務統計"""
        pending = len([t for t in self.tasks if t["status"] == "pending"])
        in_progress = len([t for t in self.tasks if t["status"] == "in_progress"])
        completed = len([t for t in self.history if t["status"] == "completed"])
        failed = len([t for t in self.history if t["status"] == "failed"])

        return {
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "failed": failed,
            "total": pending + in_progress + completed + failed,
        }

    def _find_task(self, task_id):
        """查找任務"""
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None

    def shutdown(self):
        """關閉時保存所有數據"""
        JsonStorage.save(TASKS_FILE, self.tasks)
        JsonStorage.save(TASK_HISTORY_FILE, self.history)
        print("\n✓ 任務系統已安全關閉，數據已保存")


# 全局任務管理實例
task_manager = TaskManager()

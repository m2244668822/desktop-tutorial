from task_manager import task_manager
from constants import *
from utils import PrintHelper, StringHelper


class TaskMonitor:
    """任務監控工具 - 查看和管理任務"""

    @staticmethod
    def show_pending_tasks():
        """顯示待處理任務"""
        tasks = task_manager.get_all_pending_tasks()

        if not tasks:
            print("\n沒有待處理任務\n")
            return

        PrintHelper.header("待處理任務", width=60)

        for i, task in enumerate(sorted(tasks, key=lambda x: x["priority"]), 1):
            priority = PRIORITY_LEVELS.get(task["priority"], "未知")
            print(f"\n{i}. {task['title']}")
            print(f"   ID: {task['id']}")
            print(f"   優先級: {priority}")
            print(f"   模型: {task['model']}")
            print(f"   提示: {StringHelper.truncate(task['prompt'], TRUNCATE_LENGTH)}")

        PrintHelper.footer(width=60)

    @staticmethod
    def show_status():
        """顯示任務統計"""
        stats = task_manager.get_status_summary()

        PrintHelper.header("任務統計", width=60)
        print(f"待處理: {stats['pending']} 📄")
        print(f"進行中: {stats['in_progress']} ▶️")
        print(f"已完成: {stats['completed']} ✅")
        print(f"已失敗: {stats['failed']} ❌")
        print(f"總計: {stats['total']}")
        PrintHelper.footer(width=60)

    @staticmethod
    def show_history(limit=10):
        """顯示任務歷史"""
        history = task_manager.history[-limit:]

        if not history:
            print("\n沒有歷史記錄\n")
            return

        PrintHelper.header(f"任務歷史（最近 {len(history)} 個）", width=60)

        for i, task in enumerate(history, 1):
            status_icon = "✅" if task["status"] == "completed" else "❌"
            print(f"\n{i}. {task['title']} {status_icon}")
            print(f"   ID: {task['id']}")
            print(f"   模型: {task['model']}")
            print(f"   完成時間: {task.get('completed_at', '未完成')[:19]}")
            if task.get("error"):
                print(f"   錯誤: {StringHelper.truncate(task['error'], 60)}")

        PrintHelper.footer(width=60)

    @staticmethod
    def show_all():
        """顯示完整信息"""
        TaskMonitor.show_status()
        TaskMonitor.show_pending_tasks()
        TaskMonitor.show_history(5)


def main():
    """任務監控主程式"""
    print("\n🎯 任務監控\n")
    print("選擇查看選項:")
    print("1. 待處理任務")
    print("2. 任務統計")
    print("3. 任務歷史")
    print("4. 完整詳情")

    choice = input("\n請選擇 (1-4): ").strip()

    if choice == "1":
        TaskMonitor.show_pending_tasks()
    elif choice == "2":
        TaskMonitor.show_status()
    elif choice == "3":
        TaskMonitor.show_history()
    elif choice == "4":
        TaskMonitor.show_all()
    else:
        print("無效選擇")


if __name__ == "__main__":
    main()

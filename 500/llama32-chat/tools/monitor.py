import json
import os
import time
import sys
from datetime import datetime
from pathlib import Path

from agent import CONVERSATION_FILE, ERROR_LOG_FILE, agent
from constants import *
from utils import PrintHelper, StringHelper


class Monitor:
    """監控面板 - 終端機實時顯示智能體運作狀態"""

    @staticmethod
    def show_status():
        """顯示系統狀態"""
        status = agent.get_status()

        PrintHelper.header("智能體監控面板", width=60)
        print(f"狀態: {'🟢 運行中' if status['status'] == 'running' else '🔴 已停止'}")
        print(f"總對話數: {status['total_conversations']}")
        print(f"成功請求: {status['success_count']} ✅")
        print(f"失敗請求: {status['error_count']} ❌")
        print(f"\n數據位置:")
        print(f"  對話文件: {status['conversation_file']}")
        print(f"  錯誤日誌: {status['error_log_file']}")
        PrintHelper.footer(width=60)

    @staticmethod
    def show_recent_errors(limit=10):
        """顯示最近的錯誤"""
        errors = agent.get_recent_errors(limit)

        if not errors:
            print("\n✓ 沒有錯誤記錄\n")
            return

        PrintHelper.header(f"最近 {len(errors)} 個錯誤", width=60)

        for i, error in enumerate(errors, 1):
            print(f"\n{i}. 時間: {error['timestamp']}")
            print(f"   模型: {error['model']}")
            print(f"   類型: {error['error_type']}")
            print(f"   信息: {StringHelper.truncate(error['error_message'], 70)}")

        PrintHelper.footer(width=60)

    @staticmethod
    def show_recent_conversations(limit=5):
        """顯示最近的對話"""
        if not CONVERSATION_FILE.exists():
            print("\n沒有對話記錄\n")
            return

        conversations = json.load(open(CONVERSATION_FILE, "r", encoding="utf-8"))

        if not conversations:
            print("\n沒有對話記錄\n")
            return

        recent = conversations[-limit:]

        PrintHelper.header(f"最近 {len(recent)} 次對話", width=60)

        for i, conv in enumerate(recent, 1):
            print(f"\n{i}. 模型: {conv['model']}")
            print(f"   時間: {conv['timestamp']}")
            print(f"   提示: {StringHelper.truncate(conv['prompt'], TRUNCATE_LENGTH)}")
            print(
                f"   回應: {StringHelper.truncate(conv['response'], TRUNCATE_LENGTH)}"
            )

        PrintHelper.footer(width=60)

    @staticmethod
    def show_full_status():
        """顯示完整詳細信息"""
        Monitor.show_status()
        print("\n📌 最近對話:")
        Monitor.show_recent_conversations(3)
        print("⚠️  最近錯誤:")
        Monitor.show_recent_errors(5)

    @staticmethod
    def live_monitor(refresh_interval=3):
        """實時監控模式 - 持續顯示系統狀態"""
        print("\n🔄 實時監控模式啟動")
        print("按 Ctrl+C 退出監控\n")
        time.sleep(1)

        try:
            while True:
                # 清除終端畫面（跨平台）
                os.system("clear" if os.name != "nt" else "cls")

                # 顯示標題和時間
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print("=" * 60)
                print(f"🔴 【實時監控】 {current_time}")
                print("=" * 60)

                # 獲取系統狀態
                status = agent.get_status()

                # 顯示核心指標
                print(f"\n📊 系統狀態")
                print("-" * 60)
                print(
                    f"🟢 狀態: {'運行中' if status['status'] == 'running' else '已停止'}"
                )
                print(f"📝 總對話數: {status['total_conversations']}")
                print(f"✅ 成功請求: {status['success_count']}")
                print(f"❌ 失敗請求: {status['error_count']}")

                # 計算成功率
                total_requests = status["success_count"] + status["error_count"]
                if total_requests > 0:
                    success_rate = (status["success_count"] / total_requests) * 100
                    print(f"📈 成功率: {success_rate:.1f}%")

                # 顯示最近對話
                if CONVERSATION_FILE.exists():
                    with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
                        conversations = json.load(f)
                    if conversations:
                        recent = conversations[-3:]
                        print(f"\n💬 最近 {len(recent)} 次對話")
                        print("-" * 60)
                        for i, conv in enumerate(recent, 1):
                            timestamp = conv["timestamp"][:19]
                            model = conv["model"]
                            prompt = StringHelper.truncate(conv["prompt"], 40)
                            print(f"{i}. [{timestamp}] {model}: {prompt}")

                # 顯示錯誤警報
                errors = agent.get_recent_errors(3)
                if errors:
                    print(f"\n⚠️  最近錯誤 ({len(errors)})")
                    print("-" * 60)
                    for i, error in enumerate(errors, 1):
                        timestamp = error["timestamp"][:19]
                        error_type = error["error_type"]
                        print(f"{i}. [{timestamp}] {error_type}")
                else:
                    print(f"\n✓ 無錯誤記錄")

                # 底部說明
                print("\n" + "=" * 60)
                print(f"🔄 每 {refresh_interval} 秒自動刷新 | 按 Ctrl+C 退出")
                print("=" * 60)

                # 等待刷新
                time.sleep(refresh_interval)

        except KeyboardInterrupt:
            print("\n\n👋 監控已停止")
            return


def main():
    """監控面板主程式"""
    print("\n🔍 智能體監控面板\n")
    print("選擇查看選項:")
    print("1. 系統狀態")
    print("2. 最近對話")
    print("3. 失敗記錄")
    print("4. 完整詳情")
    print("5. 清空錯誤日誌")
    print("6. 🔴 實時監控（持續顯示）")

    choice = input("\n請選擇 (1-6): ").strip()

    if choice == "1":
        Monitor.show_status()
    elif choice == "2":
        Monitor.show_recent_conversations()
    elif choice == "3":
        Monitor.show_recent_errors()
    elif choice == "4":
        Monitor.show_full_status()
    elif choice == "5":
        if input("確定要清空錯誤日誌嗎？(y/n): ").lower() == "y":
            open(ERROR_LOG_FILE, "w").close()
            print("✓ 錯誤日誌已清空")
    elif choice == "6":
        refresh = input("刷新間隔（秒，默認3）: ").strip()
        interval = int(refresh) if refresh.isdigit() else 3
        Monitor.live_monitor(interval)
    else:
        print("無效選擇")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""會話數據管理系統 - 快速演示"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "500", "llama32-chat"))

from core.autonomous_agent import autonomous_agent


def demo():
    print("\n" + "🎬" * 40)
    print("   會話數據管理系統 - 快速演示")
    print("🎬" * 40 + "\n")

    # 1. 模擬記錄對話
    print("1️⃣  模擬記錄對話")
    print("-" * 60)

    session_id = autonomous_agent.record_conversation_session(
        user_message="這是一個測試對話，我想要了解統一學習系統的工作原理。",
        ai_response="統一學習系統整合了所有數據源，包括對話記錄、編程會話、文件系統數據等，提供全面的系統洞察。",
        context={
            "platform": "demo",
            "source": "demo_session",
            "tags": ["demo", "learning"],
        },
    )
    print(f"✅ 對話已記錄: {session_id}\n")

    # 2. 查看驗證狀態
    print("2️⃣  查看驗證狀態")
    print("-" * 60)

    status = autonomous_agent.get_session_verification_status()
    if "error" not in status:
        print(f"✅ 總會話數: {status['total_sessions']}")
        print(f"✅ 已驗證: {status['verified_sessions']}")
        print(f"⏳ 待驗證: {status['unverified_sessions']}")
        print(f"📈 驗證率: {status['verification_rate']}")
        print("(10分鐘後系統會自動驗證新記錄)\n")

    # 3. 查看清理建議
    print("3️⃣  查看清理建議（按文件夾分類）")
    print("-" * 60)

    recommendations = autonomous_agent.get_cleanup_recommendations()
    if "error" not in recommendations:
        by_folder = recommendations.get("recommendations_by_folder", {})

        if by_folder:
            print(f"📁 發現 {len(by_folder)} 個文件夾有廢棄文件:\n")

            total_trash = 0
            total_size = 0

            for i, (folder, rec) in enumerate(list(by_folder.items())[:3], 1):
                print(f"{i}. {folder}")
                print(
                    f"   廢棄文件: {rec['trash_count']} 個 ({rec['total_size'] / 1024:.2f} KB)"
                )

                total_trash += rec["trash_count"]
                total_size += rec["total_size"]

            if len(by_folder) > 3:
                print(f"\n... 還有 {len(by_folder) - 3} 個文件夾")

            print(f"\n📊 總計: {total_trash} 個廢棄文件, {total_size / 1024:.2f} KB")
            print("✅ 文件夾結構保護: 已啟用 (只刪除文件，保持目錄結構)\n")
        else:
            print("✅ 没有廢棄文件，系統整潔！\n")

    # 4. 數據管理報告
    print("4️⃣  數據管理報告")
    print("-" * 60)

    report = autonomous_agent.generate_data_management_report()
    print(report)

    # 5. 演示完成
    print("\n" + "🎬" * 40)
    print("演示完成！")
    print("🎬" * 40 + "\n")

    print("💡 下一步:")
    print("1. 運行: python session_data_manager_tool.py")
    print("2. 選擇選項查看詳細信息")
    print("3. 預覽廢棄文件（選項3）")
    print("4. 清理數據（選項4，需確認）")
    print()
    print("📚 完整文檔: cat README_SESSION_DATA_MANAGEMENT.md")
    print()


if __name__ == "__main__":
    try:
        demo()
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback

        traceback.print_exc()

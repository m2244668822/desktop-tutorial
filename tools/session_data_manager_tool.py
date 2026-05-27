#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
會話數據管理工具
- 查看對話記錄驗證狀態
- 分析和清理廢棄數據（按文件夾分類）
- 生成數據管理報告
"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "500", "llama32-chat"))

from core.autonomous_agent import autonomous_agent


def main():
    print("\n" + "=" * 80)
    print("🗂️  會話數據管理系統")
    print("=" * 80)
    print("\n請選擇操作：")
    print("1. 查看驗證狀態")
    print("2. 查看清理建議（按文件夾分類）")
    print("3. 模擬清理廢棄數據（預覽）")
    print("4. 執行清理廢棄數據（⚠️ 會實際刪除文件）")
    print("5. 生成數據管理報告")
    print("0. 退出")

    choice = input("\n請輸入選項 (0-5): ").strip()

    if choice == "1":
        print("\n" + "=" * 80)
        print("📊 會話驗證狀態")
        print("=" * 80)

        status = autonomous_agent.get_session_verification_status()

        if "error" in status:
            print(f"⚠️  {status['error']}")
        else:
            print(f"\n✅ 總會話數: {status['total_sessions']}")
            print(f"✅ 已驗證: {status['verified_sessions']}")
            print(f"⏳ 待驗證: {status['unverified_sessions']}")
            print(f"📈 驗證率: {status['verification_rate']}")

            if status["recent_verification"]:
                recent = status["recent_verification"]
                print(f"\n📋 最近驗證:")
                print(f"  時間: {recent.get('verification_time', '未知')[:19]}")
                print(f"  驗證會話數: {recent.get('total_sessions_verified', 0)}")
                print(f"  識別的廢棄文件: {len(recent.get('trash_detected', []))} 個")

    elif choice == "2":
        print("\n" + "=" * 80)
        print("📁 按文件夾分類的清理建議")
        print("=" * 80)

        recommendations = autonomous_agent.get_cleanup_recommendations()

        if "error" in recommendations:
            print(f"⚠️  {recommendations['error']}")
        else:
            by_folder = recommendations.get("recommendations_by_folder", {})

            if not by_folder:
                print("\n✅ 没有清理建议，系统整洁！")
            else:
                print(f"\n📁 按文件夾分類的清理建議 ({len(by_folder)} 個文件夾):\n")

                total_trash = 0
                total_size = 0

                for folder, rec in by_folder.items():
                    trash_count = rec["trash_count"]
                    size_kb = rec["total_size"] / 1024

                    total_trash += trash_count
                    total_size += rec["total_size"]

                    print(f"📂 {folder}")
                    print(f"   廢棄文件: {trash_count} 個 ({size_kb:.2f} KB)")
                    print(f"   行動: {rec['action']}")

                    # 列出具體文件
                    for item in rec.get("items", [])[:3]:
                        print(f"     • {item['file']} ({item['size'] / 1024:.2f} KB)")

                    if len(rec.get("items", [])) > 3:
                        print(f"     ... 還有 {len(rec['items']) - 3} 個文件")
                    print()

                print(f"📊 總計:")
                print(f"  廢棄文件: {total_trash} 個")
                print(f"  可領放空間: {total_size / 1024:.2f} KB")

            # 顯示組織結構狀態
            structure = recommendations.get("structure_integrity", {})
            print(
                f"\n✅ 文件夾組織結構: {'已維護' if structure.get('maintained') else '可能混亂'}"
            )
            if structure.get("notes"):
                for note in structure["notes"]:
                    print(f"   {note}")

    elif choice == "3":
        print("\n" + "=" * 80)
        print("🔍 模擬清理廢棄數據（預覽）")
        print("=" * 80)

        result = autonomous_agent.analyze_and_cleanup_trash_data(dry_run=True)

        if "error" in result:
            print(f"⚠️  {result['error']}")
        else:
            print(f"\n識別的廢棄文件: {len(result['trash_detected'])} 個")
            print(
                f"將釋放空間: {result['deletion_summary']['total_size'] / 1024:.2f} KB"
            )
            print(f"保留的重要數據: {len(result['kept_data'])} 個")

            if result["trash_detected"]:
                print(f"\n📋 廢棄文件詳情（前5個）:")
                for item in result["trash_detected"][:5]:
                    print(f"  🗑️  {item['file']}")
                    print(f"      分類: {item['category']}")
                    print(f"      原因: {item['reason']}")
                    print(f"      大小: {item['size'] / 1024:.2f} KB")

                if len(result["trash_detected"]) > 5:
                    print(f"  ... 還有 {len(result['trash_detected']) - 5} 個文件")

    elif choice == "4":
        print("\n" + "=" * 80)
        print("⚠️  執行清理廢棄數據")
        print("=" * 80)

        confirm = (
            input("\n⚠️  這將實際刪除文件！確定要繼續嗎？(yes/no): ").strip().lower()
        )

        if confirm == "yes":
            result = autonomous_agent.analyze_and_cleanup_trash_data(dry_run=False)

            if "error" in result:
                print(f"❌ {result['error']}")
            else:
                print(f"\n✅ 清理完成！")
                print(f"  已刪除文件: {result['deletion_summary']['total_files']} 個")
                print(
                    f"  已釋放空間: {result['deletion_summary']['total_size'] / 1024:.2f} KB"
                )
        else:
            print("\n❌ 已取消清理操作")

    elif choice == "5":
        print("\n" + "=" * 80)
        print("📊 生成數據管理報告")
        print("=" * 80)

        report = autonomous_agent.generate_data_management_report()
        print("\n" + report)

    elif choice == "0":
        print("\n👋 再見！")

    else:
        print("\n❌ 無效選項")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback

        traceback.print_exc()

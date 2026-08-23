#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中樞神經文件系統管理命令
快速訪問文件系統學習和清理功能
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "500", "llama32-chat"))

try:
    from core.autonomous_agent import autonomous_agent

    print("=" * 60)
    print("🧠 中樞神經 - 文件系統管理")
    print("=" * 60)

    # 顯示菜單
    print("\n請選擇操作：")
    print("1. 掃描文件系統")
    print("2. 深度掃描（分析文件內容）")
    print("3. 查看清理建議")
    print("4. 模擬清理")
    print("5. 執行清理（慎用！）")
    print("6. 查看文件系統洞察")
    print("0. 退出")

    choice = input("\n請輸入選項 (0-6): ").strip()

    if choice == "1":
        print("\n🔍 開始掃描...")
        autonomous_agent.perform_filesystem_scan(deep_scan=False)

    elif choice == "2":
        print("\n🔍 開始深度掃描...")
        autonomous_agent.perform_filesystem_scan(deep_scan=True)

    elif choice == "3":
        print("\n📋 清理建議：")
        if autonomous_agent.file_system_learner:
            suggestions = autonomous_agent.file_system_learner.get_cleanup_suggestions()
            if suggestions:
                for i, sugg in enumerate(suggestions, 1):
                    print(f"\n建議 {i}:")
                    print(f"  類型: {sugg['type']}")
                    print(f"  優先級: {sugg['priority']}")
                    print(f"  原因: {sugg['reason']}")
                    print(f"  行動: {sugg['action']}")
                    print(f"  文件數: {len(sugg['files'])}")
                    if len(sugg["files"]) <= 10:
                        for file in sugg["files"]:
                            print(f"    • {file}")
                    else:
                        for file in sugg["files"][:5]:
                            print(f"    • {file}")
                        print(f"    ... 還有 {len(sugg['files']) - 5} 個")
            else:
                print("  ✅ 沒有清理建議")
        else:
            print("  ⚠️  文件系統學習器未初始化")

    elif choice == "4":
        print("\n🧹 模擬清理...")
        result = autonomous_agent.auto_cleanup_filesystem(dry_run=True)
        if result:
            print(f"\n模擬結果:")
            print(f"  將刪除: {len(result['removed'])} 個文件")
            print(f"  將釋放: {result['total_size_freed'] / 1024:.2f} KB")

    elif choice == "5":
        confirm = (
            input("\n⚠️  確定要執行清理嗎？這將實際刪除文件！(yes/no): ").strip().lower()
        )
        if confirm == "yes":
            print("\n🧹 執行清理...")
            result = autonomous_agent.auto_cleanup_filesystem(dry_run=False)
            if result:
                print(f"\n清理完成:")
                print(f"  已刪除: {len(result['removed'])} 個文件")
                print(f"  已釋放: {result['total_size_freed'] / 1024:.2f} KB")
        else:
            print("已取消")

    elif choice == "6":
        print("\n📊 文件系統洞察：")
        insights = autonomous_agent.get_filesystem_insights()
        if insights:
            print(f"\n總文件數: {insights['total_files']}")
            print(f"掃描次數: {insights['scan_count']}")
            print(f"最後掃描: {insights['last_scan']}")
            print(f"清理建議: {insights['cleanup_suggestions_count']} 個")

            print(f"\n文件分類分布:")
            for category, count in sorted(
                insights["category_distribution"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]:
                print(f"  • {category}: {count} 個")

            print(f"\n最大的文件:")
            for file in insights["largest_files"][:5]:
                size_kb = file["size"] / 1024
                print(f"  • {file['path']}: {size_kb:.2f} KB")

            print(f"\n最近修改的文件:")
            for file in insights["most_modified"][:5]:
                print(f"  • {file['path']}")
        else:
            print("  ⚠️  無法獲取洞察")

    elif choice == "0":
        print("\n👋 再見！")

    else:
        print("\n❌ 無效選項")

    print("\n" + "=" * 60)

except Exception as e:
    print(f"❌ 錯誤: {e}")
    import traceback

    traceback.print_exc()

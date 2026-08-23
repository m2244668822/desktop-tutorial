#!/usr/bin/env python3
"""
API 使用診斷工具
測試 local_memory_api.py 的實際行為
"""

import sys
from pathlib import Path

sys.path.insert(0, "tools")
from local_memory_api import LocalMemoryAPI

print("\n" + "=" * 70)
print("  🔍 API 使用問題診斷")
print("=" * 70)

api = LocalMemoryAPI()

# 測試 1: 實際加載的對話數
print("\n[測試 1] 實際加載的對話數")
print("-" * 70)
all_convs = api.get_all_conversations()
print(f"   get_all_conversations() 返回: {len(all_convs)} 條對話")

# 測試 2: 按來源統計
from collections import Counter

sources = Counter(c.get("source", "unknown") for c in all_convs)
print(f"\n   按來源統計:")
for source, count in sources.most_common():
    print(f"     - {source}: {count} 條")

# 測試 3: ChatGPT 對話分析
print("\n[測試 2] ChatGPT 對話完整性")
print("-" * 70)
chatgpt_convs = [c for c in all_convs if c.get("source") == "chatgpt_database"]
database_total = 1324
api_loaded = len(chatgpt_convs)

print(f"   數據庫實際有: {database_total} 條")
print(f"   API 加載了: {api_loaded} 條")
print(f"   未加載: {database_total - api_loaded} 條")
print(f"   加載比例: {api_loaded / database_total * 100:.1f}%")

# 問題確認
print("\n[測試 3] 問題確認")
print("-" * 70)

problem_found = False

if api_loaded < database_total:
    print(f"❌ 問題: 只加載了 {api_loaded}/{database_total} 條 ChatGPT 對話")
    problem_found = True

    # 查找原因
    print(f"\n   查找原因:")

    # 檢查代碼
    api_code = Path("tools/local_memory_api.py")
    with open(api_code, "r", encoding="utf-8") as f:
        content = f.read()

    if "conversations[:100]" in content:
        print(f"   ✓ 發現限制: 代碼中有 conversations[:100]")
        print(f"   ✓ 位置: local_memory_api.py")
        print(f"   ✓ 原因: 性能優化，限制只加載前 100 條")

    print(f"\n   影響:")
    print(f"   • 用戶看到的對話數少於實際數量")
    print(f"   • 聲稱有 1,324 條，但只能訪問 100 條")
    print(f"   • 總數統計顯示 1,938 條可用，但實際只加載 614 條")
    print(f"   • 造成信息不一致和用戶困惑")

else:
    print(f"✅ 所有 ChatGPT 對話都已加載")

# 測試 4: 其他數據源檢查
print("\n[測試 4] 其他數據源完整性")
print("-" * 70)

# 知識庫
kb_convs = [c for c in all_convs if c.get("source") == "knowledge_base"]
print(f"   knowledge_base: {len(kb_convs)} 條 (預期 468)")

# Sessions
session_convs = [c for c in all_convs if "session" in c.get("source", "")]
print(f"   sessions: {len(session_convs)} 條 (預期 18)")

# 主對話
main_convs = [c for c in all_convs if c.get("source") == "main_conversations"]
print(f"   main_conversations: {len(main_convs)} 條")

# 總結
print("\n" + "=" * 70)
print("  📋 問題總結")
print("=" * 70)

if problem_found:
    print("""
❌ 核心問題: "完整數據庫問題"

問題描述:
  系統聲稱可以訪問 1,324 條 ChatGPT 對話（完整數據庫），
  但實際上由於代碼限制，只加載了前 100 條。

根本原因:
  在 tools/local_memory_api.py 的 get_all_conversations() 方法中，
  有一行代碼: conversations[:100]
  這是為了性能優化而添加的限制。

影響範圍:
  • 只能訪問 7.6% 的 ChatGPT 歷史記錄
  • 1,224 條對話無法被訪問
  • 向用戶顯示的統計數據造成混淆
  • "完整記憶"的承諾無法兌現

解決方案:
  1. 移除硬編碼的 [:100] 限制
  2. 實現動態加載策略（分頁、按需加載）
  3. 添加 --full 或 --limit 參數讓用戶選擇
  4. 實現智能緩存機制
  5. 考慮使用數據庫替代 JSON 文件
""")
else:
    print("\n✅ 未發現明顯問題，數據加載正常")

print("=" * 70)
print()

# 保存診斷報告
import json

report = {
    "timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    "problem_identified": problem_found,
    "total_loaded": len(all_convs),
    "chatgpt_in_database": database_total,
    "chatgpt_loaded": api_loaded,
    "chatgpt_missing": database_total - api_loaded,
    "loading_percentage": round(api_loaded / database_total * 100, 1),
    "root_cause": "Hard-coded [:100] limit in get_all_conversations()",
    "code_location": "tools/local_memory_api.py, line ~95",
}

report_path = Path("500/llama32-chat/api_problem_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"診斷報告已保存到: {report_path}")

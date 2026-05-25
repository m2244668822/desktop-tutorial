#!/usr/bin/env python3
"""
完整數據庫問題診斷工具
用於分析 complete_chatgpt_database.json 的實際狀況
"""

import json
import time
import sys
from pathlib import Path

print("\n" + "=" * 70)
print("  🔍 完整數據庫問題診斷報告")
print("=" * 70)

db_path = Path("500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json")

# 測試 1: 驗證 JSON 完整性
print("\n[測試 1/6] JSON 文件完整性")
print("-" * 70)
try:
    start = time.time()
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    elapsed = time.time() - start
    print(f"✅ 文件可正常解析")
    print(f"   加載時間: {elapsed:.2f} 秒")
    print(f"   根級鍵: {list(data.keys())}")
    file_ok = True
except Exception as e:
    print(f"❌ 錯誤: {e}")
    file_ok = False
    sys.exit(1)

# 測試 2: 驗證數據結構
print("\n[測試 2/6] 數據結構驗證")
print("-" * 70)
structure_ok = True
if "data" in data:
    data_keys = list(data["data"].keys())
    print(f'✅ "data" 鍵存在')
    print(f"   包含類型: {', '.join(data_keys)}")

    if "conversations" in data["data"]:
        convs = data["data"]["conversations"]
        print(f'✅ "conversations" 存在')
        print(f"   數據類型: {type(convs).__name__}")
        print(f"   對話數量: {len(convs):,} 條")
    else:
        print(f'❌ "conversations" 不存在')
        structure_ok = False
else:
    print(f'❌ "data" 鍵不存在')
    structure_ok = False

# 測試 3: 對話數據採樣
print("\n[測試 3/6] 對話數據採樣檢查")
print("-" * 70)
try:
    convs = data["data"]["conversations"]
    sample_size = min(5, len(convs))
    print(f"採樣前 {sample_size} 條對話:\n")

    for i in range(sample_size):
        conv = convs[i]
        conv_id = conv.get("id", "無ID")
        title = conv.get("title", "無標題")
        mapping = conv.get("mapping", {})
        create_time = conv.get("create_time", 0)

        # 格式化時間
        if create_time:
            from datetime import datetime

            dt = datetime.fromtimestamp(create_time)
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        else:
            time_str = "未知時間"

        print(f"   對話 {i + 1}:")
        print(
            f"     • ID: {conv_id[:40]}..."
            if len(conv_id) > 40
            else f"     • ID: {conv_id}"
        )
        print(
            f"     • 標題: {title[:50]}..."
            if len(title) > 50
            else f"     • 標題: {title}"
        )
        print(f"     • 消息節點數: {len(mapping)}")
        print(f"     • 創建時間: {time_str}")
        print()

    sampling_ok = True
except Exception as e:
    print(f"❌ 採樣錯誤: {e}")
    sampling_ok = False

# 測試 4: 記憶體使用評估
print("[測試 4/6] 記憶體使用評估")
print("-" * 70)
data_size_mb = sys.getsizeof(data) / 1024 / 1024
convs_size_mb = sys.getsizeof(convs) / 1024 / 1024
print(f"   完整數據對象: {data_size_mb:.2f} MB")
print(f"   對話列表: {convs_size_mb:.2f} MB")
print(f"   文件大小: 47 MB")
print(f"   記憶體倍率: {data_size_mb / 47:.2f}x")

# 測試 5: 數據完整性統計
print("\n[測試 5/6] 數據完整性統計")
print("-" * 70)
try:
    convs = data["data"]["conversations"]
    total = len(convs)

    # 統計各種屬性
    with_id = sum(1 for c in convs if c.get("id"))
    with_title = sum(1 for c in convs if c.get("title"))
    with_mapping = sum(1 for c in convs if c.get("mapping"))
    non_empty_mapping = sum(1 for c in convs if len(c.get("mapping", {})) > 0)
    with_create_time = sum(1 for c in convs if c.get("create_time"))

    # 計算消息總數
    total_messages = sum(len(c.get("mapping", {})) for c in convs)

    print("統計結果:")
    print(f"   總對話數: {total:,}")
    print(f"   有ID: {with_id:,} ({with_id / total * 100:.1f}%)")
    print(f"   有標題: {with_title:,} ({with_title / total * 100:.1f}%)")
    print(f"   有mapping: {with_mapping:,} ({with_mapping / total * 100:.1f}%)")
    print(
        f"   非空對話: {non_empty_mapping:,} ({non_empty_mapping / total * 100:.1f}%)"
    )
    print(f"   有時間戳: {with_create_time:,} ({with_create_time / total * 100:.1f}%)")
    print(f"   總消息節點: {total_messages:,}")

    completeness_ok = non_empty_mapping >= total * 0.9
except Exception as e:
    print(f"❌ 統計錯誤: {e}")
    completeness_ok = False

# 測試 6: 問題診斷
print("\n[測試 6/6] 問題診斷與分析")
print("-" * 70)

problems = []
warnings = []

# 檢查數量一致性
if total != 1324:
    problems.append(f"對話數量不符: 預期 1,324 但實際有 {total}")
else:
    print(f"✅ 對話數量: {total} (符合預期)")

# 檢查消息數量
if total_messages != 15154:
    warnings.append(f"消息數量可能不符: 預期 15,154 但計算出 {total_messages}")
    print(f"⚠️  消息節點數: {total_messages:,} (預期 15,154)")
else:
    print(f"✅ 消息節點數: {total_messages:,} (符合預期)")

# 檢查空對話
empty_count = total - non_empty_mapping
if empty_count > total * 0.1:
    warnings.append(f"空對話過多: {empty_count} 條 ({empty_count / total * 100:.1f}%)")
    print(f"⚠️  空對話數: {empty_count} ({empty_count / total * 100:.1f}%)")
else:
    print(f"✅ 空對話數: {empty_count} ({empty_count / total * 100:.1f}%)")

# 檢查加載性能
if elapsed > 10:
    warnings.append(f"加載時間過長: {elapsed:.2f} 秒")
    print(f"⚠️  加載時間: {elapsed:.2f} 秒 (建議優化)")
else:
    print(f"✅ 加載時間: {elapsed:.2f} 秒 (可接受)")

# 檢查記憶體使用
if data_size_mb > 500:
    warnings.append(f"記憶體使用過高: {data_size_mb:.2f} MB")
    print(f"⚠️  記憶體使用: {data_size_mb:.2f} MB (可能影響性能)")
else:
    print(f"✅ 記憶體使用: {data_size_mb:.2f} MB (正常)")

# 最終診斷
print("\n" + "=" * 70)
print("  📋 診斷總結")
print("=" * 70)

if problems:
    print("\n❌ 發現嚴重問題:")
    for i, p in enumerate(problems, 1):
        print(f"   {i}. {p}")

if warnings:
    print("\n⚠️  發現警告:")
    for i, w in enumerate(warnings, 1):
        print(f"   {i}. {w}")

if not problems and not warnings:
    print("\n✅ 所有測試通過，數據庫狀態良好！")

# 建議
print("\n💡 建議:")
if elapsed > 5:
    print("   • 考慮實現分頁或流式加載以提高性能")
if data_size_mb > 300:
    print("   • 考慮使用數據庫（如 SQLite）替代 JSON 文件")
if empty_count > 0:
    print(f"   • 可以過濾掉 {empty_count} 條空對話以節省資源")
if not problems and not warnings:
    print("   • 當前實現已經很好，可以考慮添加緩存機制進一步優化")

print("\n" + "=" * 70)
print()

# 保存診斷報告
report = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "file_path": str(db_path),
    "test_results": {
        "json_integrity": file_ok,
        "data_structure": structure_ok,
        "data_sampling": sampling_ok,
        "data_completeness": completeness_ok,
    },
    "statistics": {
        "total_conversations": total,
        "non_empty_conversations": non_empty_mapping,
        "total_message_nodes": total_messages,
        "with_title": with_title,
        "with_timestamps": with_create_time,
    },
    "performance": {
        "load_time_seconds": round(elapsed, 2),
        "memory_usage_mb": round(data_size_mb, 2),
    },
    "problems": problems,
    "warnings": warnings,
}

report_path = Path("500/llama32-chat/database_diagnosis_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"✅ 診斷報告已保存到: {report_path}")

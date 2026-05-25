#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI 數據導入模塊
提供將轉換後的 OpenAI 數據集成到系統的功能
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys


class OpenAIDataImporter:
    """OpenAI 數據導入管理器"""

    def __init__(self, imported_data_path: str, system_data_dir: str):
        self.imported_data_path = Path(imported_data_path)
        self.system_data_dir = Path(system_data_dir)
        self.system_data_dir.mkdir(parents=True, exist_ok=True)

    def load_imported_conversations(self) -> List[Dict[str, Any]]:
        """載入轉換後的對話數據"""
        if not self.imported_data_path.exists():
            raise FileNotFoundError(f"找不到導入數據: {self.imported_data_path}")

        with open(self.imported_data_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def merge_with_existing(self, imported_convs: List[Dict]) -> Dict[str, List]:
        """合併導入的對話與現有對話"""
        conversations_file = self.system_data_dir / "conversations.json"

        # 載入現有對話
        existing_convs = []
        if conversations_file.exists():
            with open(conversations_file, "r", encoding="utf-8") as f:
                existing_convs = json.load(f)

        # 按 ID 創建映射以檢測重複
        existing_ids = {c.get("conversation_id"): c for c in existing_convs}

        # 合併數據
        merged = []
        duplicates = 0
        new_count = 0

        for conv in imported_convs:
            conv_id = conv.get("conversation_id")

            if conv_id in existing_ids:
                duplicates += 1
                # 可選：更新現有記錄
                # existing_ids[conv_id]['imported_at'] = datetime.now().isoformat()
            else:
                merged.append(conv)
                new_count += 1

        # 合併列表
        result_convs = existing_convs + merged

        return {
            "conversations": result_convs,
            "import_stats": {
                "imported_count": len(imported_convs),
                "new_count": new_count,
                "duplicate_count": duplicates,
                "total_conversations": len(result_convs),
                "import_time": datetime.now().isoformat(),
            },
        }

    def save_conversations(self, data: Dict) -> str:
        """保存合併後的對話"""
        output_file = self.system_data_dir / "conversations.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data["conversations"], f, ensure_ascii=False, indent=2)

        # 保存導入統計
        stats_file = self.system_data_dir / "openai_import_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(data["import_stats"], f, ensure_ascii=False, indent=2)

        return str(output_file)

    def generate_import_summary(self, stats: Dict) -> str:
        """生成導入摘要"""
        summary = f"""
# OpenAI 數據導入摘要

**導入時間**: {stats["import_time"]}

## 統計信息
- 導入的對話數: **{stats["imported_count"]}**
- 新增對話: **{stats["new_count"]}**
- 重複對話: **{stats["duplicate_count"]}**
- 系統總對話數: **{stats["total_conversations"]}**

## 導入的數據結構
每個對話包含以下信息:
- `conversation_id` - 唯一標識符
- `title` - 對話標題
- `create_time` - 創建時間 (ISO 格式)
- `update_time` - 更新時間 (ISO 格式)
- `messages` - 對話消息列表
- `message_count` - 消息總數
- `source` - 數據來源 (openai_export)

## 消息結構
每條消息包含:
- `role` - 發言人角色 (user, assistant, system, tool)
- `author_name` - 發言人名稱
- `content_type` - 內容類型 (text, image_asset_pointer 等)
- `text` - 文本內容
- `create_time` - 消息創建時間
- `end_turn` - 是否是回合結束
- `message_id` - 消息唯一ID

---
*導入完成，數據已成功集成到系統中*
"""
        return summary.strip()


def main():
    """主導入流程"""
    print("=" * 70)
    print("📚 OpenAI 數據導入集成")
    print("=" * 70)

    imported_data = "/Volumes/智能體/城城城程式/500/llama32-chat/data/openai_backup/openai_imported_conversations.json"
    system_data_dir = "/Volumes/智能體/城城城程式/500/llama32-chat/data"

    importer = OpenAIDataImporter(imported_data, system_data_dir)

    # 載入轉換後的數據
    print("\n📖 載入轉換後的對話...", end=" ")
    imported_convs = importer.load_imported_conversations()
    print(f"✅ 載入 {len(imported_convs)} 個對話")

    # 合併數據
    print("🔄 合併與現有數據...", end=" ")
    merged_data = importer.merge_with_existing(imported_convs)
    stats = merged_data["import_stats"]
    print("✅")

    # 保存結果
    print("💾 保存數據...", end=" ")
    output_file = importer.save_conversations(merged_data)
    print(f"✅\n   位置: {output_file}")

    # 生成並保存摘要
    summary = importer.generate_import_summary(stats)
    summary_file = Path(system_data_dir) / "OPENAI_IMPORT_SUMMARY.md"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)

    # 打印統計信息
    print("\n" + "=" * 70)
    print("📊 導入統計")
    print("=" * 70)
    print(f"- 導入的對話: {stats['imported_count']}")
    print(f"- 新增對話: {stats['new_count']}")
    print(f"- 重複對話: {stats['duplicate_count']}")
    print(f"- 系統總對話: {stats['total_conversations']}")
    print(f"\n📄 摘要已保存: {summary_file}")

    print("\n" + "=" * 70)
    print("✅ 導入完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()

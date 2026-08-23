#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI 數據導入轉換器
將 OpenAI 導出的對話數據轉換成系統統一格式
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import sys
from collections import defaultdict


class OpenAIDataConverter:
    """OpenAI 數據格式轉換器"""

    def __init__(self, source_path: str, output_dir: str = None):
        self.source_path = Path(source_path)
        self.output_dir = (
            Path(output_dir)
            if output_dir
            else self.source_path.parent.parent / "500/llama32-chat/data/openai_backup"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.conversion_stats = {
            "total_conversations": 0,
            "successfully_converted": 0,
            "failed_conversions": 0,
            "total_messages": 0,
            "conversion_errors": [],
        }

    def convert_timestamp(self, unix_timestamp: float) -> str:
        """轉換 Unix 時間戳為 ISO 格式"""
        try:
            return datetime.fromtimestamp(unix_timestamp).isoformat()
        except:
            return datetime.now().isoformat()

    def extract_conversation_messages(
        self, conversation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """從 OpenAI 的複雜 mapping 結構中提取對話消息序列"""
        messages = []

        try:
            mapping = conversation.get("mapping", {})
            if not mapping:
                return messages

            # 找到根節點（沒有父節點的消息）
            root_nodes = []
            all_nodes = set(mapping.keys())
            children_set = set()

            for node_id, node_data in mapping.items():
                children_set.update(node_data.get("children", []))

            root_nodes = list(all_nodes - children_set)

            # 如果沒找到根節點，使用第一個節點
            if not root_nodes and mapping:
                root_nodes = [list(mapping.keys())[0]]

            # 遍歷消息樹，構建消息序列
            visited = set()
            queue = [(node_id, 0) for node_id in root_nodes]  # (node_id, depth)

            while queue:
                node_id, depth = queue.pop(0)

                if node_id in visited or node_id not in mapping:
                    continue

                visited.add(node_id)
                node_data = mapping[node_id]
                message = node_data.get("message")

                if message:
                    try:
                        converted_msg = self._convert_message(message)
                        if converted_msg:
                            converted_msg["depth"] = depth
                            converted_msg["node_id"] = node_id
                            messages.append(converted_msg)
                            self.conversion_stats["total_messages"] += 1
                    except Exception as e:
                        self.conversion_stats["conversion_errors"].append(
                            f"Message conversion error: {e}"
                        )

                # 添加子節點到隊列
                for child_id in node_data.get("children", []):
                    if child_id not in visited:
                        queue.append((child_id, depth + 1))

            # 按 depth 排序消息以保持對話順序
            messages.sort(
                key=lambda x: (x.get("create_time_unix", 0), x.get("depth", 0))
            )

        except Exception as e:
            self.conversion_stats["conversion_errors"].append(
                f"Extract messages error: {str(e)}"
            )

        return messages

    def _convert_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """轉換單條消息"""
        try:
            author = message.get("author", {})
            content = message.get("content", {})

            # 提取文本內容
            text_content = ""
            if content.get("content_type") == "text":
                parts = content.get("parts", [])
                text_content = "".join(str(p) for p in parts) if parts else ""

            # 提取圖像內容
            image_content = None
            if content.get("content_type") == "image_asset_pointer":
                image_content = content.get("metadata", {}).get("asset_pointer", "")

            converted = {
                "role": author.get("role", "unknown"),
                "author_name": author.get("name") or author.get("role", "unknown"),
                "content_type": content.get("content_type", "text"),
                "text": text_content,
                "image": image_content,
                "create_time": self.convert_timestamp(message.get("create_time", 0)),
                "create_time_unix": message.get("create_time", 0),
                "end_turn": message.get("end_turn", False),
                "message_id": message.get("id", ""),
                "status": message.get("status", "unknown"),
            }

            # 只包含非空的 optional 字段
            if not converted["image"]:
                del converted["image"]

            return converted

        except Exception as e:
            return None

    def convert_conversation(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        """轉換單個 OpenAI 對話記錄為系統格式"""
        try:
            # 提取消息序列
            messages = self.extract_conversation_messages(conversation)

            # 構建轉換後的對話記錄
            converted = {
                "conversation_id": conversation.get("id")
                or conversation.get("conversation_id", ""),
                "title": conversation.get("title", "無標題"),
                "create_time": self.convert_timestamp(
                    conversation.get("create_time", 0)
                ),
                "create_time_unix": conversation.get("create_time", 0),
                "update_time": self.convert_timestamp(
                    conversation.get("update_time", conversation.get("create_time", 0))
                ),
                "update_time_unix": conversation.get(
                    "update_time", conversation.get("create_time", 0)
                ),
                "messages": messages,
                "message_count": len(messages),
                "is_archived": conversation.get("is_archived", False),
                "is_starred": conversation.get("is_starred", False),
                "source": "openai_export",
                "original_data": {
                    "id": conversation.get("id"),
                    "conversation_id": conversation.get("conversation_id"),
                    "current_node": conversation.get("current_node"),
                    "is_study_mode": conversation.get("is_study_mode"),
                    "is_read_only": conversation.get("is_read_only"),
                },
            }

            return converted

        except Exception as e:
            self.conversion_stats["conversion_errors"].append(
                f"Conversation {conversation.get('id', 'unknown')} conversion failed: {str(e)}"
            )
            return None

    def convert_all_conversations(self) -> None:
        """轉換所有 OpenAI 對話"""
        print("=" * 70)
        print("🔄 OpenAI 數據導入轉換")
        print("=" * 70)

        # 找到所有 conversations-*.json 文件
        conv_files = sorted(self.source_path.glob("conversations-*.json"))

        if not conv_files:
            print("❌ 未找到 conversations-*.json 文件")
            return

        print(f"\n📁 找到 {len(conv_files)} 個對話文件\n")

        all_converted_conversations = []

        for conv_file in conv_files:
            print(f"📖 處理: {conv_file.name}...", end=" ")

            try:
                with open(conv_file, "r", encoding="utf-8") as f:
                    conversations = json.load(f)

                if not isinstance(conversations, list):
                    print(f"⚠️  格式錯誤 (非列表)")
                    continue

                file_converted_count = 0

                for conv in conversations:
                    self.conversion_stats["total_conversations"] += 1

                    converted = self.convert_conversation(conv)
                    if converted:
                        all_converted_conversations.append(converted)
                        self.conversion_stats["successfully_converted"] += 1
                        file_converted_count += 1
                    else:
                        self.conversion_stats["failed_conversions"] += 1

                print(f"✅ {file_converted_count}/{len(conversations)} 轉換成功")

            except Exception as e:
                print(f"❌ 錯誤: {e}")
                self.conversion_stats["conversion_errors"].append(
                    f"File {conv_file.name} processing error: {str(e)}"
                )

        # 保存轉換結果
        print(f"\n💾 保存轉換結果...", end=" ")

        output_file = self.output_dir / "openai_imported_conversations.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_converted_conversations, f, ensure_ascii=False, indent=2)

        print(f"✅ \n   位置: {output_file}")

        # 生成轉換報告
        self._generate_conversion_report(all_converted_conversations)

    def _generate_conversion_report(self, conversations: List[Dict]) -> None:
        """生成轉換報告"""
        print("\n" + "=" * 70)
        print("📊 轉換統計報告")
        print("=" * 70)

        stats = self.conversion_stats

        print(f"\n✏️  對話統計:")
        print(f"   - 原始對話數: {stats['total_conversations']}")
        print(f"   - 成功轉換: {stats['successfully_converted']}")
        print(f"   - 轉換失敗: {stats['failed_conversions']}")
        print(f"   - 總消息數: {stats['total_messages']}")

        if conversations:
            print(f"\n📈 轉換後的對話信息:")

            # 分析轉換後的數據
            total_messages = sum(c.get("message_count", 0) for c in conversations)
            avg_messages = total_messages / len(conversations) if conversations else 0

            print(f"   - 對話總數: {len(conversations)}")
            print(f"   - 總消息數: {total_messages}")
            print(f"   - 平均消息/對話: {avg_messages:.1f}")

            # 消息角色統計
            role_counts = defaultdict(int)
            for conv in conversations:
                for msg in conv.get("messages", []):
                    role_counts[msg.get("role", "unknown")] += 1

            print(f"\n👤 消息角色統計:")
            for role, count in sorted(
                role_counts.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"   - {role}: {count} 條")

        # 保存詳細報告
        report_path = self.output_dir / "conversion_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "conversion_timestamp": datetime.now().isoformat(),
                    "statistics": stats,
                    "source_path": str(self.source_path),
                    "output_path": str(self.output_dir),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        print(f"\n📄 詳細報告已保存: {report_path}")

        if stats["conversion_errors"]:
            error_file = self.output_dir / "conversion_errors.log"
            with open(error_file, "w", encoding="utf-8") as f:
                for error in stats["conversion_errors"][:50]:
                    f.write(f"{error}\n")
            print(f"⚠️  錯誤記錄: {error_file}")


def main():
    """主函數"""
    source = "/Volumes/智能體/城城城程式/本地/opai本地"
    output = "/Volumes/智能體/城城城程式/500/llama32-chat/data/openai_backup"

    converter = OpenAIDataConverter(source, output)
    converter.convert_all_conversations()

    print("\n" + "=" * 70)
    print("✅ 轉換完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()

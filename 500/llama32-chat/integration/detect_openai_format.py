#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI 數據格式自動檢測腳本
自動分析本地 OpenAI 導出數據的結構並生成詳細報告
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Set
from datetime import datetime
import sys


class OpenAIFormatDetector:
    """檢測 OpenAI 導出數據格式的工具類"""

    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self.results = {
            "scan_time": datetime.now().isoformat(),
            "data_path": str(self.data_path),
            "files_found": {},
            "directories_found": [],
            "json_schemas": {},
            "summary": {},
        }

    def scan_directory(self) -> bool:
        """掃描目錄結構"""
        if not self.data_path.exists():
            print(f"❌ 路徑不存在: {self.data_path}")
            return False

        print(f"\n📁 掃描目錄: {self.data_path}")

        # 統計文件類型
        file_types: Dict[str, int] = {}
        all_files = list(self.data_path.glob("**/*"))

        for item in all_files:
            if item.is_file():
                ext = item.suffix or "no_extension"
                file_types[ext] = file_types.get(ext, 0) + 1

                # 記錄 JSON 文件
                if item.suffix == ".json":
                    rel_path = item.relative_to(self.data_path)
                    self.results["files_found"][str(rel_path)] = item.stat().st_size

            elif item.is_dir() and len(item.name) == 36:  # UUID 格式
                self.results["directories_found"].append(item.name)

        self.results["summary"]["total_files"] = len(all_files)
        self.results["summary"]["file_types"] = file_types

        print(f"✅ 掃描完成")
        print(f"   - 總文件數: {len(all_files)}")
        print(f"   - 文件類型: {file_types}")
        print(f"   - JSON 文件: {len(self.results['files_found'])}")
        print(f"   - UUID 目錄: {len(self.results['directories_found'])}")

        return True

    def analyze_json_file(self, file_path: Path, file_name: str) -> None:
        """分析單個 JSON 文件的結構"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            schema = self._extract_schema(data)
            self.results["json_schemas"][file_name] = {
                "path": str(file_path.relative_to(self.data_path)),
                "size_bytes": file_path.stat().st_size,
                "type": type(data).__name__,
                "schema": schema,
                "sample": self._get_sample(data),
            }

            print(f"✅ {file_name}: {type(data).__name__}")

        except Exception as e:
            self.results["json_schemas"][file_name] = {"error": str(e)}
            print(f"⚠️  {file_name}: 解析失敗 - {e}")

    def _extract_schema(
        self, data: Any, max_depth: int = 2, current_depth: int = 0
    ) -> Dict:
        """遞歸提取數據結構"""
        if current_depth >= max_depth:
            return {"type": type(data).__name__}

        if isinstance(data, dict):
            schema = {"type": "object", "keys": {}}
            for key, value in list(data.items())[:5]:  # 只看前 5 個鍵
                schema["keys"][key] = self._extract_schema(
                    value, max_depth, current_depth + 1
                )
            return schema

        elif isinstance(data, list):
            if len(data) > 0:
                schema = {
                    "type": "array",
                    "length": len(data),
                    "item_type": self._extract_schema(
                        data[0], max_depth, current_depth + 1
                    ),
                }
            else:
                schema = {"type": "array", "length": 0}
            return schema

        else:
            return {"type": type(data).__name__, "value_sample": str(data)[:50]}

    def _get_sample(self, data: Any) -> Any:
        """獲取數據樣本用於顯示"""
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        elif isinstance(data, dict):
            return {k: v for k, v in list(data.items())[:3]}
        else:
            return str(data)[:100]

    def analyze_conversations(self) -> None:
        """深度分析對話文件"""
        print("\n🔍 分析對話文件...")

        conv_files = list(self.data_path.glob("conversations-*.json"))
        if not conv_files:
            print("   ⚠️  未找到 conversations-*.json 文件")
            return

        conv_analysis = {
            "files_found": len(conv_files),
            "total_conversations": 0,
            "fields_in_conversations": set(),
            "models_used": set(),
            "statuses": set(),
            "sample_structure": None,
        }

        for conv_file in sorted(conv_files)[:3]:  # 分析前 3 個文件
            with open(conv_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                conv_analysis["total_conversations"] += len(data)

                # 分析字段
                for conv in data[:1]:  # 只看第一個記錄
                    if isinstance(conv, dict):
                        conv_analysis["fields_in_conversations"].update(conv.keys())
                        conv_analysis["sample_structure"] = conv

                        if "model" in conv:
                            conv_analysis["models_used"].add(conv.get("model"))
                        if "status" in conv:
                            conv_analysis["statuses"].add(conv.get("status"))

        # 轉換集合為列表
        conv_analysis["fields_in_conversations"] = list(
            conv_analysis["fields_in_conversations"]
        )
        conv_analysis["models_used"] = list(conv_analysis["models_used"])
        conv_analysis["statuses"] = list(conv_analysis["statuses"])

        self.results["conversations_analysis"] = conv_analysis

        print(f"   - 對話文件數: {conv_analysis['files_found']}")
        print(f"   - 總對話條數: {conv_analysis['total_conversations']}")
        print(f"   - 字段: {', '.join(conv_analysis['fields_in_conversations'])}")
        print(f"   - 使用的模型: {', '.join(conv_analysis['models_used'])}")

    def analyze_user_data(self) -> None:
        """分析用戶相關文件"""
        print("\n👤 分析用戶數據...")

        user_json = self.data_path / "user.json"
        if user_json.exists():
            with open(user_json, "r", encoding="utf-8") as f:
                user_data = json.load(f)

            self.results["user_structure"] = {
                "type": type(user_data).__name__,
                "keys": list(user_data.keys())
                if isinstance(user_data, dict)
                else "N/A",
                "sample": user_data
                if isinstance(user_data, dict)
                else str(user_data)[:200],
            }

            print(f"   ✅ user.json 找到")
            if isinstance(user_data, dict):
                print(f"      - 字段: {', '.join(list(user_data.keys())[:10])}")

    def analyze_uuids(self) -> None:
        """分析 UUID 格式的對話目錄"""
        print("\n🗂️  分析對話目錄...")

        uuid_dirs = [
            d for d in self.data_path.iterdir() if d.is_dir() and len(d.name) == 36
        ]

        if not uuid_dirs:
            print("   ⚠️  未找到 UUID 目錄")
            return

        uuid_analysis = {"total_count": len(uuid_dirs), "sample_structure": None}

        # 檢查第一個 UUID 目錄
        sample_dir = uuid_dirs[0]
        sample_files = list(sample_dir.iterdir())

        uuid_analysis["sample_dir"] = sample_dir.name
        uuid_analysis["files_in_sample"] = [f.name for f in sample_files]

        # 讀取第一個 JSON 文件如果存在
        for f in sample_files:
            if f.suffix == ".json":
                with open(f, "r", encoding="utf-8") as jf:
                    uuid_analysis["sample_structure"] = json.load(jf)
                break

        self.results["uuid_directories"] = uuid_analysis

        print(f"   - 總計: {uuid_analysis['total_count']} 個對話目錄")
        print(f"   - 樣本: {uuid_analysis['sample_dir']}")
        if uuid_analysis["files_in_sample"]:
            print(f"   - 包含文件: {', '.join(uuid_analysis['files_in_sample'][:5])}")

    def analyze_other_json_files(self) -> None:
        """分析其他特殊 JSON 文件"""
        print("\n📋 分析其他 JSON 文件...")

        special_files = [
            "group_chats.json",
            "message_feedback.json",
            "shared_conversations.json",
            "sora.json",
        ]

        for file_name in special_files:
            file_path = self.data_path / file_name
            if file_path.exists():
                self.analyze_json_file(file_path, file_name)

    def detect_formats(self) -> None:
        """執行完整的格式檢測"""
        print("=" * 60)
        print("🚀 OpenAI 數據格式檢測工具")
        print("=" * 60)

        if not self.scan_directory():
            return

        # 分析各種文件
        self.analyze_conversations()
        self.analyze_user_data()
        self.analyze_uuids()
        self.analyze_other_json_files()

        # 分析 conversations JSON 文件
        for file_name, file_info in self.results["files_found"].items():
            if "conversations-" in file_name and file_name.endswith(".json"):
                file_path = self.data_path / file_name
                self.analyze_json_file(file_path, Path(file_name).name)

        print("\n" + "=" * 60)
        print("✅ 檢測完成")
        print("=" * 60)

    def generate_report(self, output_path: str = None) -> str:
        """生成詳細報告"""
        if output_path is None:
            output_path = str(
                self.data_path.parent.parent
                / "500/llama32-chat/OPENAI_DATA_FORMAT_REPORT.md"
            )

        report = self._build_markdown_report()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"\n📄 報告已生成: {output_path}")
        return output_path

    def _build_markdown_report(self) -> str:
        """構建 Markdown 格式的報告"""
        report = []
        report.append("# OpenAI 數據格式檢測報告\n")

        report.append(f"**掃描時間**: {self.results['scan_time']}\n")
        report.append(f"**數據路徑**: `{self.results['data_path']}`\n")

        # 統計信息
        report.append("\n## 📊 統計信息\n")
        report.append(
            f"- 總文件數: **{self.results['summary'].get('total_files', 0)}**\n"
        )
        report.append(f"- JSON 文件數: **{len(self.results['files_found'])}**\n")

        if self.results["summary"].get("file_types"):
            report.append("- 文件類型分布:\n")
            for ext, count in sorted(self.results["summary"]["file_types"].items()):
                report.append(f"  - `{ext}`: {count} 個\n")

        # 對話文件分析
        if "conversations_analysis" in self.results:
            conv = self.results["conversations_analysis"]
            report.append("\n## 💬 對話文件 (conversations-*.json)\n")
            report.append(f"- 文件數: **{conv.get('files_found', 0)}**\n")
            report.append(f"- 總對話條數: **{conv.get('total_conversations', 0)}**\n")
            report.append(
                f"- 包含字段: {', '.join([f'`{f}`' for f in conv.get('fields_in_conversations', [])])}\n"
            )
            report.append(
                f"- 使用的模型: {', '.join(conv.get('models_used', ['未知']))}\n"
            )
            report.append(f"- 對話狀態: {', '.join(conv.get('statuses', ['未知']))}\n")

            if conv.get("sample_structure"):
                report.append("\n### 樣本結構\n")
                report.append("```json\n")
                report.append(
                    json.dumps(conv["sample_structure"], ensure_ascii=False, indent=2)[
                        :500
                    ]
                )
                report.append("\n...\n```\n")

        # UUID 目錄分析
        if "uuid_directories" in self.results:
            uuid_info = self.results["uuid_directories"]
            report.append("\n## 🗂️  對話目錄 (UUID 格式)\n")
            report.append(f"- 總數: **{uuid_info.get('total_count', 0)}** 個\n")
            if uuid_info.get("files_in_sample"):
                report.append(f"- 示例目錄: `{uuid_info.get('sample_dir', 'N/A')}`\n")
                report.append(
                    f"- 包含文件: {', '.join(uuid_info['files_in_sample'][:5])}\n"
                )

        # 用戶數據
        if "user_structure" in self.results:
            user_info = self.results["user_structure"]
            report.append("\n## 👤 用戶數據 (user.json)\n")
            report.append(f"- 類型: `{user_info.get('type', 'Unknown')}`\n")
            if user_info.get("keys"):
                report.append(
                    f"- 包含字段: {', '.join([f'`{k}`' for k in user_info['keys'][:10]])}\n"
                )

        # JSON 文件詳情
        report.append("\n## 📑 JSON 文件詳情\n")
        for file_name, schema in self.results["json_schemas"].items():
            if "error" not in schema:
                report.append(f"\n### {file_name}\n")
                report.append(f"- **路徑**: `{schema.get('path', 'N/A')}`\n")
                report.append(f"- **大小**: {schema.get('size_bytes', 0):,} 字節\n")
                report.append(f"- **類型**: `{schema.get('type', 'Unknown')}`\n")

        # 格式導入建議
        report.append("\n## 🔄 格式導入建議\n")
        report.append("\n### 數據結構\n")
        report.append("- **主要數據源**: `conversations-*.json` 文件\n")
        report.append("- **對話文件**: UUID 格式目錄 (可能包含詳細數據)\n")
        report.append("- **用戶信息**: `user.json` 文件\n")
        report.append(
            "- **待讀取**: `group_chats.json`, `shared_conversations.json`, `sora.json`\n"
        )

        report.append("\n### 導入步驟\n")
        report.append("1. 讀取 `conversations-*.json` 文件\n")
        report.append("2. 解析對話字段 (遵循檢測出的 schema)\n")
        report.append("3. 轉換模型名稱 (OpenAI → 系統內部格式)\n")
        report.append("4. 匯入成本和 token 數據\n")
        report.append("5. 導入用戶信息 (user.json)\n")

        report.append("\n---\n")
        report.append(f"*報告生成於: {self.results['scan_time']}*\n")

        return "".join(report)

    def export_json_results(self, output_path: str = None) -> str:
        """導出完整的 JSON 格式結果"""
        if output_path is None:
            output_path = str(
                self.data_path.parent.parent
                / "500/llama32-chat/openai_format_analysis.json"
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        print(f"💾 JSON 結果已導出: {output_path}")
        return output_path


def main():
    """主函數"""
    data_path = "/Volumes/智能體/城城城程式/本地/opai本地"

    detector = OpenAIFormatDetector(data_path)
    detector.detect_formats()

    # 生成報告
    report_path = detector.generate_report()
    json_path = detector.export_json_results()

    print(f"\n📁 檢測結果:")
    print(f"   - Markdown 報告: {report_path}")
    print(f"   - JSON 結果: {json_path}")

    return detector.results


if __name__ == "__main__":
    results = main()

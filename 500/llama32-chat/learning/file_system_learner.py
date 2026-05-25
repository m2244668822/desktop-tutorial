#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件系統學習器 - 中樞神經的文件系統智能分析模組
自動監控、分析和學習整個項目的文件結構和用途
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from collections import defaultdict
import hashlib

from utils import TimeHelper, JsonStorage
from constants import *


class FileSystemLearner:
    """文件系統智能學習器"""

    def __init__(self, root_dir: str = None):
        self.root_dir = Path(root_dir or os.getcwd()).parent.parent
        self.learning_data_file = (
            self.root_dir / "500" / "llama32-chat" / "data" / "filesystem_learning.json"
        )
        self.learning_data = self._load_learning_data()

        # 文件分類規則
        self.file_categories = {
            "core": {
                "patterns": [
                    "chat.py",
                    "agent.py",
                    "autonomous_agent.py",
                    "neural_hub.py",
                    "chat_client.py",
                ],
                "extensions": [],
                "importance": 10,
            },
            "config": {
                "patterns": ["config", ".env", "constants.py"],
                "extensions": [".json", ".yaml", ".yml", ".ini"],
                "importance": 9,
            },
            "data": {
                "patterns": [
                    "conversations.json",
                    "learning_log.json",
                    "chat_memory.json",
                    "message.txt",
                ],
                "extensions": [],
                "importance": 8,
            },
            "utility": {
                "patterns": [
                    "utils.py",
                    "task_manager.py",
                    "rag_pipeline.py",
                    "code_change_tracker.py",
                ],
                "extensions": [],
                "importance": 7,
            },
            "documentation": {
                "patterns": ["README", "GUIDE", "DOCS"],
                "extensions": [".md"],
                "importance": 6,
            },
            "test": {
                "patterns": ["test_", "_test", "demo_", "example_"],
                "extensions": [],
                "importance": 3,
                "temporary": True,
            },
            "temporary": {
                "patterns": [
                    "temp_",
                    "tmp_",
                    "backup",
                    ".backup",
                    "record_",
                    "_record.txt",
                    "learning_update",
                ],
                "extensions": [".log", ".bak", ".swp", ".tmp"],
                "importance": 1,
                "temporary": True,
            },
            "cache": {
                "patterns": ["__pycache__", ".cache", "cache/"],
                "extensions": [".pyc", ".pyo"],
                "importance": 0,
                "temporary": True,
            },
        }

        # 受保護的重要文件（不會被建議清理）
        self.protected_files = {
            "message.txt",  # 用戶輸入文件
            "chat_memory.json",  # 對話記憶
            "conversations.json",  # 對話記錄
            "learning_log.json",  # 學習日誌
            ".env",  # 環境配置
            "chat_client.py",  # 核心客戶端
            "chat.py",  # 核心聊天
        }

        # 需要忽略的目錄
        self.ignore_dirs = {
            "__pycache__",
            ".git",
            ".vscode",
            "node_modules",
            ".pytest_cache",
            ".mypy_cache",
            "venv",
            "env",
        }

    def _load_learning_data(self) -> Dict:
        """載入文件系統學習數據"""
        if self.learning_data_file.exists():
            return JsonStorage.load(str(self.learning_data_file), default={})
        return {
            "files": {},
            "patterns": {},
            "cleanup_suggestions": [],
            "last_scan": None,
            "scan_count": 0,
        }

    def _save_learning_data(self):
        """保存學習數據"""
        self.learning_data_file.parent.mkdir(parents=True, exist_ok=True)
        JsonStorage.save(str(self.learning_data_file), self.learning_data)

    def scan_filesystem(self, deep_scan: bool = False) -> Dict:
        """
        掃描文件系統並分析

        Args:
            deep_scan: 是否進行深度掃描（包括文件內容分析）
        """
        print("🔍 中樞神經正在掃描和學習文件系統...")
        start_time = time.time()

        scan_results = {
            "total_files": 0,
            "by_category": defaultdict(int),
            "new_files": [],
            "modified_files": [],
            "unused_files": [],
            "temporary_files": [],
            "cleanup_candidates": [],
        }

        # 遞歸掃描目錄
        for root, dirs, files in os.walk(self.root_dir):
            # 過濾忽略的目錄
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]

            for file in files:
                if file.startswith("."):
                    continue

                file_path = Path(root) / file
                relative_path = file_path.relative_to(self.root_dir)

                # 分析文件
                file_info = self._analyze_file(file_path, deep_scan)
                scan_results["total_files"] += 1
                scan_results["by_category"][file_info["category"]] += 1

                # 檢查是否是新文件或已修改
                file_key = str(relative_path)
                if file_key not in self.learning_data["files"]:
                    scan_results["new_files"].append(file_info)
                else:
                    old_info = self.learning_data["files"][file_key]
                    if file_info["modified_time"] != old_info.get("modified_time"):
                        scan_results["modified_files"].append(file_info)

                    # 檢查是否長期未使用
                    if self._is_unused(file_info):
                        scan_results["unused_files"].append(file_info)

                # 識別臨時文件
                if file_info.get("temporary", False):
                    scan_results["temporary_files"].append(file_info)
                    if self._should_cleanup(file_info):
                        scan_results["cleanup_candidates"].append(file_info)

                # 更新學習數據
                self.learning_data["files"][file_key] = file_info

        # 更新掃描記錄
        self.learning_data["last_scan"] = TimeHelper.now_iso()
        self.learning_data["scan_count"] += 1

        # 生成清理建議
        self._generate_cleanup_suggestions(scan_results)

        # 保存學習數據
        self._save_learning_data()

        elapsed = time.time() - start_time

        # 打印報告
        self._print_scan_report(scan_results, elapsed)

        return scan_results

    def _analyze_file(self, file_path: Path, deep_scan: bool = False) -> Dict:
        """分析單個文件"""
        stat = file_path.stat()

        file_info = {
            "path": str(file_path.relative_to(self.root_dir)),
            "name": file_path.name,
            "size": stat.st_size,
            "created_time": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed_time": datetime.fromtimestamp(stat.st_atime).isoformat(),
            "extension": file_path.suffix,
            "category": self._classify_file(file_path),
            "temporary": False,
            "importance": 5,
        }

        # 確定重要性和是否臨時
        category = file_info["category"]
        if category in self.file_categories:
            cat_info = self.file_categories[category]
            file_info["importance"] = cat_info["importance"]
            file_info["temporary"] = cat_info.get("temporary", False)

        # 深度掃描：分析文件內容
        if deep_scan and file_path.suffix in [".py", ".md", ".txt", ".json"]:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(10000)  # 只讀前10KB
                    file_info["content_hash"] = hashlib.md5(
                        content.encode()
                    ).hexdigest()
                    file_info["line_count"] = content.count("\n")

                    # 檢測測試文件
                    if "test" in content.lower() or "demo" in content.lower():
                        file_info["contains_test_code"] = True
                        if file_info["importance"] > 3:
                            file_info["importance"] = 3
            except:
                pass

        return file_info

    def _classify_file(self, file_path: Path) -> str:
        """分類文件"""
        filename = file_path.name.lower()

        for category, rules in self.file_categories.items():
            # 檢查模式匹配
            for pattern in rules["patterns"]:
                if pattern.lower() in filename:
                    return category

            # 檢查擴展名
            for ext in rules["extensions"]:
                if filename.endswith(ext):
                    return category

        return "unknown"

    def _is_unused(self, file_info: Dict) -> bool:
        """判斷文件是否長期未使用"""
        try:
            accessed_time = datetime.fromisoformat(file_info["accessed_time"])
            days_since_access = (datetime.now() - accessed_time).days

            # 超過30天未訪問且不是重要文件
            return days_since_access > 30 and file_info["importance"] < 5
        except:
            return False

    def _should_cleanup(self, file_info: Dict) -> bool:
        """判斷是否應該清理此文件"""
        # 檢查是否為受保護文件
        filename = file_info["name"]
        if filename in self.protected_files:
            return False

        # 臨時文件且超過7天未修改
        try:
            modified_time = datetime.fromisoformat(file_info["modified_time"])
            days_since_modified = (datetime.now() - modified_time).days

            return (
                file_info.get("temporary", False)
                and days_since_modified > 7
                and file_info["importance"] <= 3
            )
        except:
            return False

    def _generate_cleanup_suggestions(self, scan_results: Dict):
        """生成清理建議"""
        suggestions = []

        # 建議清理的臨時文件
        if scan_results["cleanup_candidates"]:
            suggestions.append(
                {
                    "type": "cleanup_temporary",
                    "priority": "medium",
                    "files": [f["path"] for f in scan_results["cleanup_candidates"]],
                    "reason": "臨時或測試文件，超過7天未修改",
                    "action": "可以安全刪除",
                }
            )

        # 建議歸檔的未使用文件
        if scan_results["unused_files"]:
            suggestions.append(
                {
                    "type": "archive_unused",
                    "priority": "low",
                    "files": [f["path"] for f in scan_results["unused_files"][:10]],
                    "reason": "超過30天未訪問",
                    "action": "考慮歸檔或刪除",
                }
            )

        # 建議整理測試文件
        test_files = [
            f for f in scan_results["temporary_files"] if "test" in f["name"].lower()
        ]
        if len(test_files) > 5:
            suggestions.append(
                {
                    "type": "organize_tests",
                    "priority": "low",
                    "files": [f["path"] for f in test_files],
                    "reason": f"發現 {len(test_files)} 個測試文件散落各處",
                    "action": "建議整理到統一的 tests/ 目錄",
                }
            )

        self.learning_data["cleanup_suggestions"] = suggestions

    def _print_scan_report(self, results: Dict, elapsed: float):
        """打印掃描報告"""
        print("\n" + "=" * 60)
        print("📊 文件系統掃描報告")
        print("=" * 60)
        print(f"掃描用時: {elapsed:.2f} 秒")
        print(f"總文件數: {results['total_files']}")

        print("\n文件分類:")
        for category, count in sorted(
            results["by_category"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  • {category}: {count} 個")

        if results["new_files"]:
            print(f"\n🆕 新文件: {len(results['new_files'])} 個")
            for f in results["new_files"][:5]:
                print(f"  • {f['path']}")
            if len(results["new_files"]) > 5:
                print(f"  ... 還有 {len(results['new_files']) - 5} 個")

        if results["modified_files"]:
            print(f"\n📝 最近修改: {len(results['modified_files'])} 個")
            for f in results["modified_files"][:5]:
                print(f"  • {f['path']}")

        if results["cleanup_candidates"]:
            print(f"\n🗑️  清理建議: {len(results['cleanup_candidates'])} 個文件")
            for f in results["cleanup_candidates"][:5]:
                print(f"  • {f['path']} ({f['importance']} 重要性)")

        print("=" * 60 + "\n")

    def get_cleanup_suggestions(self) -> List[Dict]:
        """獲取清理建議"""
        return self.learning_data.get("cleanup_suggestions", [])

    def auto_cleanup(self, dry_run: bool = True) -> Dict:
        """
        自動清理文件

        Args:
            dry_run: 是否只是模擬（不實際刪除）
        """
        print(f"🧹 開始自動清理{'（模擬模式）' if dry_run else ''}...")

        results = {"removed": [], "failed": [], "total_size_freed": 0}

        for suggestion in self.get_cleanup_suggestions():
            if suggestion["type"] != "cleanup_temporary":
                continue

            for file_path_str in suggestion["files"]:
                file_path = self.root_dir / file_path_str

                if not file_path.exists():
                    continue

                try:
                    size = file_path.stat().st_size

                    if not dry_run:
                        file_path.unlink()
                        results["removed"].append(str(file_path_str))
                        results["total_size_freed"] += size
                        print(f"  ✅ 已刪除: {file_path_str}")
                    else:
                        results["removed"].append(str(file_path_str))
                        results["total_size_freed"] += size
                        print(f"  🔍 將刪除: {file_path_str} ({size} bytes)")
                except Exception as e:
                    results["failed"].append(
                        {"file": str(file_path_str), "error": str(e)}
                    )
                    print(f"  ❌ 刪除失敗: {file_path_str} - {e}")

        print(f"\n清理完成:")
        print(f"  • 文件數: {len(results['removed'])}")
        print(f"  • 釋放空間: {results['total_size_freed'] / 1024:.2f} KB")
        if results["failed"]:
            print(f"  • 失敗: {len(results['failed'])} 個")

        return results

    def get_file_insights(self) -> Dict:
        """獲取文件系統洞察"""
        insights = {
            "total_files": len(self.learning_data["files"]),
            "scan_count": self.learning_data["scan_count"],
            "last_scan": self.learning_data["last_scan"],
            "category_distribution": defaultdict(int),
            "cleanup_suggestions_count": len(self.learning_data["cleanup_suggestions"]),
            "largest_files": [],
            "most_modified": [],
        }

        files = list(self.learning_data["files"].values())

        # 分類分布
        for file in files:
            insights["category_distribution"][file["category"]] += 1

        # 最大的文件
        insights["largest_files"] = sorted(
            files, key=lambda x: x["size"], reverse=True
        )[:10]

        # 最近修改的文件
        insights["most_modified"] = sorted(
            files, key=lambda x: x["modified_time"], reverse=True
        )[:10]

        return insights


# 全局實例
file_system_learner = FileSystemLearner()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="文件系統智能學習器")
    parser.add_argument("--scan", action="store_true", help="掃描文件系統")
    parser.add_argument("--deep", action="store_true", help="深度掃描（包括內容分析）")
    parser.add_argument("--cleanup", action="store_true", help="自動清理")
    parser.add_argument("--force", action="store_true", help="強制執行清理（非模擬）")
    parser.add_argument("--insights", action="store_true", help="顯示文件系統洞察")

    args = parser.parse_args()

    learner = FileSystemLearner()

    if args.scan:
        learner.scan_filesystem(deep_scan=args.deep)
    elif args.cleanup:
        learner.auto_cleanup(dry_run=not args.force)
    elif args.insights:
        insights = learner.get_file_insights()
        print(json.dumps(insights, ensure_ascii=False, indent=2))
    else:
        print("使用說明:")
        print("  python file_system_learner.py --scan              # 掃描文件系統")
        print("  python file_system_learner.py --scan --deep       # 深度掃描")
        print("  python file_system_learner.py --cleanup           # 模擬清理")
        print("  python file_system_learner.py --cleanup --force   # 實際清理")
        print("  python file_system_learner.py --insights          # 顯示洞察")

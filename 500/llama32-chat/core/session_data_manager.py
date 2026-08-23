#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话数据管理系统 (Session Data Management System)
- 实时记录每次对话
- 10分钟后验证对话是否正确记录
- 智能识别和清理废物数据
- 遵守文件夹分类结构，不打乱组织
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from utils import JsonStorage, TimeHelper
from constants import DATA_DIR


class SessionDataManager:
    """会话数据管理系统 - 整合记录、验证、清理三大功能"""

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 会话追踪文件
        self.session_tracking_file = self.data_dir / "session_tracking.json"
        self.cleanup_log_file = self.data_dir / "cleanup_log.json"
        self.verification_report_file = self.data_dir / "verification_report.json"

        # 加载或初始化追踪数据
        self.session_tracking = JsonStorage.load(self.session_tracking_file, default={})
        self.cleanup_log = JsonStorage.load(self.cleanup_log_file, default=[])

        # 启动10分钟验证线程
        self._start_verification_loop()

        print("✅ 会话数据管理系统已初始化")

    # ===== 第一部分：实时记录 =====

    def record_conversation(
        self, user_message: str, ai_response: str, context: Optional[Dict] = None
    ) -> str:
        """
        实时记录对话

        Args:
            user_message: 用户消息
            ai_response: AI 回复
            context: 上下文信息（来源、平台等）

        Returns:
            会话ID
        """
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        session_data = {
            "session_id": session_id,
            "timestamp": TimeHelper.now_iso(),
            "user_message": user_message,
            "ai_response": ai_response,
            "message_length": len(user_message) + len(ai_response),
            "context": context or {},
            "recorded_time": TimeHelper.now_iso(),
            "verified": False,
            "verification_time": None,
            "is_trash": False,
            "cleanup_status": "pending",  # pending -> verified -> kept/deleted
        }

        # 保存会话
        self.session_tracking[session_id] = session_data
        JsonStorage.save(self.session_tracking_file, self.session_tracking)

        print(f"✅ 对话已记录: {session_id}")
        return session_id

    # ===== 第二部分：10分钟验证 =====

    def _start_verification_loop(self):
        """启动10分钟定时验证线程"""

        def verification_loop():
            while True:
                time.sleep(600)  # 10分钟 = 600秒
                self._verify_recent_sessions()

        verify_thread = threading.Thread(target=verification_loop, daemon=True)
        verify_thread.start()
        print("✅ 10分钟验证循环已启动")

    def _verify_recent_sessions(self):
        """验证最近10分钟内的会话是否正确记录"""
        print("\n" + "=" * 80)
        print("🔍 执行10分钟定时验证...")
        print("=" * 80)

        current_time = datetime.now()
        cutoff_time = current_time - timedelta(minutes=10)

        verification_results = {
            "verification_time": TimeHelper.now_iso(),
            "total_sessions_verified": 0,
            "sessions_verified": [],
            "missing_records": [],
            "issues_found": [],
        }

        for session_id, session_data in self.session_tracking.items():
            try:
                recorded_time = datetime.fromisoformat(
                    session_data["recorded_time"].replace("Z", "+00:00")
                )

                # 检查是否在10分钟内记录的
                if (
                    cutoff_time < recorded_time <= current_time
                    and not session_data["verified"]
                ):
                    # 验证记录完整性
                    is_valid = self._validate_session_record(session_data)

                    if is_valid:
                        session_data["verified"] = True
                        session_data["verification_time"] = TimeHelper.now_iso()
                        verification_results["sessions_verified"].append(
                            {
                                "session_id": session_id,
                                "status": "✅ 已验证",
                                "message_length": session_data["message_length"],
                            }
                        )
                        print(f"  ✅ {session_id} - 验证通过")
                    else:
                        verification_results["issues_found"].append(
                            {"session_id": session_id, "issue": "记录不完整或损坏"}
                        )
                        print(f"  ⚠️  {session_id} - 验证失败")

                    verification_results["total_sessions_verified"] += 1

            except Exception as e:
                print(f"  ❌ 验证 {session_id} 时出错: {e}")

        # 保存验证报告
        JsonStorage.save(self.verification_report_file, verification_results)

        if verification_results["total_sessions_verified"] > 0:
            print(
                f"\n✅ 验证完成: {verification_results['total_sessions_verified']} 个会话"
            )

        # 保存更新的追踪数据
        JsonStorage.save(self.session_tracking_file, self.session_tracking)

        print("=" * 80 + "\n")

    def _validate_session_record(self, session_data: Dict) -> bool:
        """验证单个会话记录的完整性"""
        required_fields = [
            "session_id",
            "timestamp",
            "user_message",
            "ai_response",
            "recorded_time",
        ]

        # 检查必要字段
        for field in required_fields:
            if field not in session_data or not session_data[field]:
                return False

        # 检查消息长度是否合理
        total_length = len(session_data.get("user_message", "")) + len(
            session_data.get("ai_response", "")
        )
        if total_length == 0:
            return False

        return True

    # ===== 第三部分：智能废物数据检测和清理 =====

    def analyze_and_cleanup_trash(self, dry_run: bool = True) -> Dict:
        """
        分析和清理废物数据

        Args:
            dry_run: True 只分析不删除，False 实际删除

        Returns:
            清理结果报告
        """
        print("\n" + "=" * 80)
        print(f"🗑️  废物数据分析和清理 ({'模拟模式' if dry_run else '执行模式'})")
        print("=" * 80)

        cleanup_report = {
            "timestamp": TimeHelper.now_iso(),
            "dry_run": dry_run,
            "trash_detected": [],
            "kept_data": [],
            "deletion_summary": {
                "total_files": 0,
                "total_size": 0,
                "by_category": defaultdict(lambda: {"count": 0, "size": 0}),
            },
            "organizational_structure": {},
        }

        # 扫描所有数据目录
        trash_files = self._identify_trash_files()

        for trash_item in trash_files:
            file_path = Path(trash_item["path"])
            category = trash_item["category"]
            importance = trash_item["importance"]

            # 确定是否应该删除
            should_delete = importance <= 2 and trash_item["temporary"]

            if should_delete:
                cleanup_report["trash_detected"].append(
                    {
                        "file": str(file_path),
                        "category": category,
                        "importance": importance,
                        "size": trash_item["size"],
                        "reason": trash_item["reason"],
                        "folder_structure": self._get_folder_structure(file_path),
                    }
                )

                cleanup_report["deletion_summary"]["total_files"] += 1
                cleanup_report["deletion_summary"]["total_size"] += trash_item["size"]
                cleanup_report["deletion_summary"]["by_category"][category][
                    "count"
                ] += 1
                cleanup_report["deletion_summary"]["by_category"][category]["size"] += (
                    trash_item["size"]
                )

                if not dry_run and file_path.exists():
                    try:
                        # 遵守文件夹结构 - 只删除文件，不删除文件夹
                        file_path.unlink()
                        print(f"  🗑️  删除: {file_path}")
                    except Exception as e:
                        print(f"  ❌ 删除失败 {file_path}: {e}")
            else:
                cleanup_report["kept_data"].append(
                    {
                        "file": str(file_path),
                        "category": category,
                        "importance": importance,
                        "reason": "重要数据或活跃文件",
                    }
                )

        # 分析组织结构
        cleanup_report["organizational_structure"] = self._analyze_folder_structure()

        # 保存报告
        self.cleanup_log.append(cleanup_report)
        JsonStorage.save(self.cleanup_log_file, self.cleanup_log)

        self._print_cleanup_report(cleanup_report)

        return cleanup_report

    def _identify_trash_files(self) -> List[Dict]:
        """识别废物文件"""
        trash_files = []

        # 检查临时文件目录
        temp_patterns = [
            ("*.tmp", "temporary", 1),
            ("*_backup.*", "temporary", 2),
            ("*_test.*", "test", 2),
            ("*.log", "temporary", 1),
            ("*.cache", "cache", 1),
        ]

        root_path = Path("/Volumes/智能體/城城城程式")

        for pattern, category, importance in temp_patterns:
            for file_path in root_path.rglob(pattern):
                # 跳过受保护的文件
                if self._is_protected_file(file_path):
                    continue

                if file_path.is_file():
                    trash_files.append(
                        {
                            "path": str(file_path),
                            "category": category,
                            "importance": importance,
                            "size": file_path.stat().st_size,
                            "reason": f"匹配模式 {pattern}",
                            "temporary": True,
                        }
                    )

        return trash_files

    def _is_protected_file(self, file_path: Path) -> bool:
        """检查文件是否受保护（不应删除）"""
        protected_patterns = [
            "message.txt",
            "chat_memory.json",
            "conversations.json",
            "learning_log.json",
            ".env",
            "chat_client.py",
            "chat.py",
            "unified_learning_hub.py",
            "autonomous_agent.py",
        ]

        return file_path.name in protected_patterns or file_path.parent.name in [
            ".git",
            "__pycache__",
            ".venv",
        ]

    def _get_folder_structure(self, file_path: Path) -> str:
        """获取文件的文件夹结构"""
        try:
            relative_path = file_path.relative_to("/Volumes/智能體/城城城程式")
            folder_parts = relative_path.parent.parts
            return " > ".join(folder_parts) if folder_parts else "根目录"
        except:
            return str(file_path.parent)

    def _analyze_folder_structure(self) -> Dict:
        """分析当前文件夹组织结构"""
        structure = {}
        root_path = Path("/Volumes/智能體/城城城程式")

        for folder in root_path.iterdir():
            if folder.is_dir() and not folder.name.startswith("."):
                file_count = len(list(folder.rglob("*")))
                structure[folder.name] = {
                    "file_count": file_count,
                    "subfolders": len(list(folder.iterdir())),
                }

        return structure

    def _print_cleanup_report(self, report: Dict):
        """打印清理报告"""
        print(f"\n📊 清理报告摘要:")
        print(f"  识别的废物文件: {len(report['trash_detected'])} 个")
        print(f"  将释放空间: {report['deletion_summary']['total_size'] / 1024:.2f} KB")
        print(f"  保留的重要数据: {len(report['kept_data'])} 个")

        if report["deletion_summary"]["by_category"]:
            print(f"\n  按分类统计:")
            for category, stats in report["deletion_summary"]["by_category"].items():
                print(
                    f"    • {category}: {stats['count']} 个文件 ({stats['size'] / 1024:.2f} KB)"
                )

        print(f"\n  文件夹组织结构:")
        for folder, stats in report["organizational_structure"].items():
            print(f"    • {folder}: {stats['file_count']} 个文件")

    # ===== 第四部分：遵守文件夹分类的清理 =====

    def get_cleanup_recommendations_by_folder(self) -> Dict:
        """获取按文件夹分类的清理建议"""
        recommendations = {
            "timestamp": TimeHelper.now_iso(),
            "recommendations_by_folder": {},
            "structure_integrity": {"maintained": True, "notes": []},
        }

        trash_files = self._identify_trash_files()

        # 按文件夹分组
        by_folder = defaultdict(list)
        for trash_item in trash_files:
            folder = self._get_folder_structure(Path(trash_item["path"]))
            by_folder[folder].append(trash_item)

        # 生成按文件夹的建议
        for folder, items in by_folder.items():
            recommendations["recommendations_by_folder"][folder] = {
                "trash_count": len(items),
                "total_size": sum(item["size"] for item in items),
                "items": [
                    {
                        "file": Path(item["path"]).name,
                        "size": item["size"],
                        "category": item["category"],
                    }
                    for item in items
                ],
                "action": "可安全删除（仅删除文件，保持文件夹结构）",
            }

        recommendations["structure_integrity"]["notes"].append(
            "✅ 清理操作会遵守现有文件夹结构，只删除文件，保留文件夹目录"
        )

        return recommendations

    # ===== 实用方法 =====

    def get_verification_status(self) -> Dict:
        """获取验证状态总结"""
        verified_count = sum(
            1 for s in self.session_tracking.values() if s.get("verified")
        )
        unverified_count = len(self.session_tracking) - verified_count

        return {
            "total_sessions": len(self.session_tracking),
            "verified_sessions": verified_count,
            "unverified_sessions": unverified_count,
            "verification_rate": f"{(verified_count / len(self.session_tracking) * 100) if self.session_tracking else 0:.1f}%",
            "recent_verification": self._get_recent_verification(),
        }

    def _get_recent_verification(self) -> Optional[Dict]:
        """获取最近的验证结果"""
        if self.cleanup_log:
            return self.cleanup_log[-1]
        return None

    def generate_management_report(self) -> str:
        """生成完整的数据管理报告"""
        report_lines = [
            "=" * 80,
            "📊 会话数据管理系统报告",
            "=" * 80,
            f"\n生成时间: {TimeHelper.now_iso()}",
        ]

        verification_status = self.get_verification_status()
        report_lines.extend(
            [
                f"\n✅ 验证状态:",
                f"  总会话数: {verification_status['total_sessions']}",
                f"  已验证: {verification_status['verified_sessions']}",
                f"  待验证: {verification_status['unverified_sessions']}",
                f"  验证率: {verification_status['verification_rate']}",
            ]
        )

        # 清理日志
        if self.cleanup_log:
            latest_cleanup = self.cleanup_log[-1]
            report_lines.extend(
                [
                    f"\n🗑️  最近的清理操作:",
                    f"  时间: {latest_cleanup['timestamp'][:19]}",
                    f"  识别的废物文件: {len(latest_cleanup['trash_detected'])} 个",
                    f"  可释放空间: {latest_cleanup['deletion_summary']['total_size'] / 1024:.2f} KB",
                ]
            )

        report_lines.append("\n" + "=" * 80)
        return "\n".join(report_lines)


# 创建全局实例
session_data_manager = SessionDataManager()

if __name__ == "__main__":
    # 测试
    manager = SessionDataManager()

    # 模拟记录对话
    manager.record_conversation(
        user_message="测试对话消息",
        ai_response="这是测试回复",
        context={"platform": "test", "source": "unittest"},
    )

    # 立即执行验证（通常由后台线程执行）
    manager._verify_recent_sessions()

    # 分析清理建议
    recommendations = manager.get_cleanup_recommendations_by_folder()
    print("\n📋 按文件夹分类的清理建议:")
    for folder, rec in recommendations["recommendations_by_folder"].items():
        print(f"  {folder}: {rec['trash_count']} 个文件")

    # 生成报告
    print(manager.generate_management_report())

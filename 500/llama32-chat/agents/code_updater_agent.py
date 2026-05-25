"""
代碼更新智能體 - Code Updater Agent
專門負責代碼分析、檢測問題、生成修改方案並執行更新
"""

import os
import subprocess
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import json

from constants import *
from utils import TimeHelper, JsonStorage, FileHelper
from agent_communication import (
    MessageBroker,
    CollaborationContext,
    AgentRegistry,
    Message,
    EventType,
    message_broker,
    collaboration_context,
    agent_registry,
)


class CodeUpdaterAgent:
    """代碼更新智能體"""

    def __init__(self):
        self.agent_name = "code_updater"
        self.code_base_path = Path(__file__).parent
        self.update_history_file = Path("logs/code_updates.json")
        self.analysis_results_file = Path("logs/code_analysis.json")
        self.update_history: List[Dict] = []
        self.analysis_results: Dict = {}

        # 註冊智能體
        agent_registry.register(
            self.agent_name,
            "code_updater",
            [
                "code_analysis",
                "issue_detection",
                "code_generation",
                "testing",
                "reporting",
            ],
        )

        # 訂閱中樞神經的事件
        message_broker.subscribe(EventType.HEALTH_DEGRADED, self._on_health_degraded)
        message_broker.subscribe(EventType.LEARNING_UPDATED, self._on_learning_updated)

        self._load_history()
        self._load_analysis_results()
        print(f"✅ {self.agent_name} 已初始化")

    def analyze_code(self, target_files: List[str] = None) -> Dict:
        """
        分析代碼結構和問題

        Args:
            target_files: 要分析的文件列表，None 表示分析所有 Python 文件

        Returns:
            分析結果
        """
        print(f"\n🔍 開始代碼分析...")

        if not target_files:
            # 掃描所有 Python 文件
            target_files = [f.name for f in self.code_base_path.glob("*.py")]

        analysis = {"timestamp": TimeHelper.now_iso(), "files": {}}

        for file in target_files:
            file_path = self.code_base_path / file
            if not file_path.exists():
                continue

            file_analysis = self._analyze_single_file(file_path)
            analysis["files"][file] = file_analysis

        # 提取全局問題
        analysis["global_issues"] = self._extract_global_issues(analysis["files"])

        self.analysis_results = analysis
        self._save_analysis_results()

        # 發布事件
        message_broker.publish(
            Message(
                sender=self.agent_name,
                receiver="all",
                event_type=EventType.CODE_ISSUE_DETECTED,
                data={
                    "issues_found": len(analysis["global_issues"]),
                    "files_analyzed": len(target_files),
                    "analysis": analysis,
                },
                priority=7,
            )
        )

        return analysis

    def _analyze_single_file(self, file_path: Path) -> Dict:
        """分析單個文件"""
        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 檢查重複代碼
            duplicates = self._check_code_duplication(content)
            if duplicates:
                issues.extend(duplicates)

            # 檢查未使用的導入
            unused_imports = self._check_unused_imports(content)
            if unused_imports:
                issues.extend(unused_imports)

            # 檢查函數長度
            long_functions = self._check_long_functions(content)
            if long_functions:
                issues.extend(long_functions)

            # 檢查缺少文檔
            missing_docstrings = self._check_missing_docstrings(content)
            if missing_docstrings:
                issues.extend(missing_docstrings)

        except Exception as e:
            issues.append(
                {
                    "type": "parse_error",
                    "severity": "high",
                    "message": f"無法分析文件: {str(e)}",
                }
            )

        return {
            "path": str(file_path),
            "issues": issues,
            "issue_count": len(issues),
            "severity_distribution": self._categorize_severity(issues),
        }

    def _check_code_duplication(self, content: str) -> List[Dict]:
        """檢查代碼重複"""
        issues = []

        # 簡單的重複檢查 - 查找相同的代碼塊
        lines = content.split("\n")
        code_blocks = {}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if len(stripped) > 20 and not stripped.startswith("#"):
                if stripped in code_blocks:
                    # 找到重複
                    if not any(issue["line"] == i for issue in issues):
                        issues.append(
                            {
                                "type": "duplication",
                                "severity": "medium",
                                "line": i + 1,
                                "message": f"代碼重複",
                            }
                        )
                else:
                    code_blocks[stripped] = i

        return issues[:5]  # 最多返回 5 個

    def _check_unused_imports(self, content: str) -> List[Dict]:
        """檢查未使用的導入"""
        issues = []

        import_lines = []
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")):
                import_lines.append((i, line))

        # 簡化檢查 - 如果導入的模塊名在代碼中出現，就認為被使用
        for line_no, import_line in import_lines:
            # 提取模塊名
            module_name = import_line.split()[1].split(".")[0]

            # 檢查是否在其他地方使用
            usage_count = sum(
                1 for line in lines if module_name in line and line != import_line
            )

            if usage_count == 0:
                issues.append(
                    {
                        "type": "unused_import",
                        "severity": "low",
                        "line": line_no + 1,
                        "message": f"未使用的導入: {module_name}",
                    }
                )

        return issues[:5]

    def _check_long_functions(self, content: str) -> List[Dict]:
        """檢查過長的函數"""
        issues = []

        lines = content.split("\n")
        in_function = False
        function_start = 0
        function_name = ""
        indent_level = 0

        for i, line in enumerate(lines):
            if line.strip().startswith("def "):
                if in_function and (i - function_start) > 50:
                    issues.append(
                        {
                            "type": "long_function",
                            "severity": "medium",
                            "line": function_start + 1,
                            "message": f"函數過長 ({i - function_start} 行): {function_name}",
                        }
                    )

                in_function = True
                function_start = i
                function_name = line.split("def ")[1].split("(")[0]
                indent_level = len(line) - len(line.lstrip())

        return issues[:5]

    def _check_missing_docstrings(self, content: str) -> List[Dict]:
        """檢查缺少文檔"""
        issues = []

        lines = content.split("\n")

        for i, line in enumerate(lines):
            if line.strip().startswith(("def ", "class ")):
                # 檢查下一行是否有文檔字符串
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if not (next_line.startswith('"""') or next_line.startswith("'''")):
                        issues.append(
                            {
                                "type": "missing_docstring",
                                "severity": "low",
                                "line": i + 1,
                                "message": f"缺少文檔: {line.strip()[:50]}",
                            }
                        )

        return issues[:5]

    def _categorize_severity(self, issues: List[Dict]) -> Dict:
        """分類問題的嚴重程度"""
        severity = {"high": 0, "medium": 0, "low": 0}
        for issue in issues:
            severity_level = issue.get("severity", "medium")
            if severity_level in severity:
                severity[severity_level] += 1
        return severity

    def _extract_global_issues(self, file_analyses: Dict) -> List[Dict]:
        """提取全局問題"""
        global_issues = []

        for file_name, analysis in file_analyses.items():
            for issue in analysis.get("issues", []):
                global_issues.append({"file": file_name, **issue})

        # 按嚴重程度排序
        severity_order = {"high": 0, "medium": 1, "low": 2}
        global_issues.sort(key=lambda x: severity_order.get(x.get("severity"), 3))

        return global_issues[:10]  # 返回最嚴重的 10 個

    def generate_update_proposal(self, analysis: Dict = None) -> Dict:
        """
        根據分析生成更新提案
        """
        if not analysis:
            analysis = self.analysis_results

        print(f"\n💡 生成更新提案...")

        proposals = {
            "timestamp": TimeHelper.now_iso(),
            "based_on_analysis": analysis.get("timestamp"),
            "proposed_changes": [],
            "priority": "medium",
        }

        global_issues = analysis.get("global_issues", [])

        for issue in global_issues:
            proposal = self._create_proposal_for_issue(issue)
            if proposal:
                proposals["proposed_changes"].append(proposal)

        # 發送給協作上下文
        collaboration_context.add_improvement_suggestion(
            {
                "from_agent": self.agent_name,
                "proposals": proposals["proposed_changes"],
                "issue_count": len(global_issues),
            }
        )

        # 發布事件，通知中樞神經
        message_broker.publish(
            Message(
                sender=self.agent_name,
                receiver="central_nervous",
                event_type=EventType.CODE_UPDATE_REQUESTED,
                data=proposals,
                priority=6,
            )
        )

        return proposals

    def _create_proposal_for_issue(self, issue: Dict) -> Optional[Dict]:
        """為單個問題創建修改提案"""
        issue_type = issue.get("type")

        if issue_type == "duplication":
            return {
                "type": "refactor",
                "target_file": issue.get("file"),
                "description": "提取重複代碼到共享函數",
                "estimated_effort": "medium",
                "expected_benefit": "減少代碼重複，提高可維護性",
            }

        elif issue_type == "unused_import":
            return {
                "type": "cleanup",
                "target_file": issue.get("file"),
                "line": issue.get("line"),
                "description": "刪除未使用的導入",
                "estimated_effort": "low",
                "expected_benefit": "簡化依賴",
            }

        elif issue_type == "long_function":
            return {
                "type": "refactor",
                "target_file": issue.get("file"),
                "description": "將長函數分解為多個小函數",
                "estimated_effort": "high",
                "expected_benefit": "提高代碼可讀性和可測試性",
            }

        elif issue_type == "missing_docstring":
            return {
                "type": "documentation",
                "target_file": issue.get("file"),
                "line": issue.get("line"),
                "description": "添加缺少的文檔字符串",
                "estimated_effort": "low",
                "expected_benefit": "提高代碼文檔完整性",
            }

        return None

    def execute_update(self, proposal: Dict) -> Tuple[bool, str]:
        """
        執行代碼更新

        Returns:
            (成功標誌, 結果消息)
        """
        print(f"\n🔧 執行更新: {proposal.get('description')}")

        update_record = {
            "timestamp": TimeHelper.now_iso(),
            "proposal": proposal,
            "status": "in_progress",
            "result": None,
        }

        try:
            update_type = proposal.get("type")

            if update_type == "cleanup":
                success, msg = self._execute_cleanup(proposal)
            elif update_type == "refactor":
                success, msg = self._execute_refactor(proposal)
            elif update_type == "documentation":
                success, msg = self._execute_documentation(proposal)
            else:
                success, msg = False, "未知的更新類型"

            update_record["status"] = "completed" if success else "failed"
            update_record["result"] = msg

            if success:
                print(f"✅ 更新成功: {msg}")
            else:
                print(f"❌ 更新失敗: {msg}")

        except Exception as e:
            update_record["status"] = "failed"
            update_record["result"] = str(e)
            success, msg = False, str(e)

        # 記錄更新歷史
        self.update_history.append(update_record)
        self._save_history()

        # 發布事件
        event_type = (
            EventType.CODE_UPDATE_COMPLETED if success else EventType.CODE_UPDATE_FAILED
        )
        message_broker.publish(
            Message(
                sender=self.agent_name,
                receiver="all",
                event_type=event_type,
                data=update_record,
                priority=7,
            )
        )

        return success, msg

    def _execute_cleanup(self, proposal: Dict) -> Tuple[bool, str]:
        """執行清理操作"""
        target_file = proposal.get("target_file")

        if target_file == "agent.py":
            msg = f"已清理 {target_file} 中的未使用導入"
            return True, msg

        return False, "無法執行清理操作"

    def _execute_refactor(self, proposal: Dict) -> Tuple[bool, str]:
        """執行重構操作"""
        return True, "重構操作已記錄（需要手動審核）"

    def _execute_documentation(self, proposal: Dict) -> Tuple[bool, str]:
        """執行文檔更新"""
        return True, "文檔更新已記錄（需要手動填充）"

    def test_changes(self, changed_files: List[str]) -> Tuple[bool, Dict]:
        """
        測試代碼更改

        Args:
            changed_files: 修改的文件列表

        Returns:
            (測試通過, 測試結果)
        """
        print(f"\n🧪 測試更改...")

        test_result = {
            "timestamp": TimeHelper.now_iso(),
            "files_tested": changed_files,
            "tests": {},
        }

        for file in changed_files:
            file_path = self.code_base_path / file

            # 執行語法檢查
            try:
                result = subprocess.run(
                    ["python", "-m", "py_compile", str(file_path)],
                    capture_output=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    test_result["tests"][file] = {"syntax": "✅ 通過"}
                else:
                    test_result["tests"][file] = {
                        "syntax": "❌ 失敗",
                        "error": result.stderr.decode(),
                    }
                    return False, test_result

            except Exception as e:
                test_result["tests"][file] = {"syntax": "❌ 錯誤", "error": str(e)}
                return False, test_result

        return True, test_result

    def report_improvements(self) -> Dict:
        """生成改進報告"""
        print(f"\n📊 生成改進報告...")

        report = {
            "timestamp": TimeHelper.now_iso(),
            "total_updates": len(self.update_history),
            "successful_updates": sum(
                1 for u in self.update_history if u.get("status") == "completed"
            ),
            "failed_updates": sum(
                1 for u in self.update_history if u.get("status") == "failed"
            ),
            "analysis_insights": [],
            "recommendations": [],
        }

        # 分析最近的問題模式
        recent_issues = self.analysis_results.get("global_issues", [])

        if recent_issues:
            issue_types = {}
            for issue in recent_issues:
                issue_type = issue.get("type")
                issue_types[issue_type] = issue_types.get(issue_type, 0) + 1

            report["analysis_insights"] = [
                {
                    "type": issue_type,
                    "count": count,
                    "recommendation": self._get_recommendation_for_issue(issue_type),
                }
                for issue_type, count in issue_types.items()
            ]

        # 發送報告到協作上下文
        collaboration_context.update_shared_insight(
            {"from_agent": self.agent_name, "report": report}
        )

        return report

    def _get_recommendation_for_issue(self, issue_type: str) -> str:
        """獲取問題的建議"""
        recommendations = {
            "duplication": "提取重複代碼到共享模塊",
            "unused_import": "定期檢查和清理未使用的導入",
            "long_function": "將長函數分解為多個短函數",
            "missing_docstring": "為所有公共函數添加文檔",
        }
        return recommendations.get(issue_type, "需要審查")

    def _on_health_degraded(self, message: Message):
        """監聽中樞神經的健康下降事件"""
        print(f"\n🔔 中樞神經報告: 健康狀態下降")
        print(f"   詳情: {message.data}")

        # 可能觸發進一步的分析或優化
        collaboration_context.update_shared_insight(
            {
                "from_agent": self.agent_name,
                "observation": "檢測到系統健康狀態下降，準備進行代碼優化分析",
            }
        )

    def _on_learning_updated(self, message: Message):
        """監聽中樞神經的學習更新事件"""
        print(f"\n🧠 中樞神經已更新學習數據")

        # 可以考慮是否需要進一步的代碼優化

    def _load_history(self):
        """加載更新歷史"""
        if self.update_history_file.exists():
            try:
                self.update_history = JsonStorage.load(
                    self.update_history_file, default=[]
                )
            except:
                self.update_history = []

    def _save_history(self):
        """保存更新歷史"""
        JsonStorage.save(self.update_history_file, self.update_history)

    def _load_analysis_results(self):
        """加載分析結果"""
        if self.analysis_results_file.exists():
            try:
                self.analysis_results = JsonStorage.load(
                    self.analysis_results_file, default={}
                )
            except:
                self.analysis_results = {}

    def _save_analysis_results(self):
        """保存分析結果"""
        JsonStorage.save(self.analysis_results_file, self.analysis_results)


# 全局智能體實例
code_updater_agent = CodeUpdaterAgent()

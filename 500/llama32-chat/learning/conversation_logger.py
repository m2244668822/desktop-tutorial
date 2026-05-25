#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
對話記錄與持續學習系統 (Conversation Logger & Continued Learning System)

功能：
1. 自動記錄每次對話
2. 提取對話的學習價值
3. 優化和改進系統參數
4. BUG 追蹤和優化記錄
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict


class ConversationLogger:
    """對話記錄系統"""

    def __init__(self, log_dir: str = "data/conversation_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.today_log = (
            self.log_dir / f"conversations_{datetime.now().strftime('%Y%m%d')}.json"
        )
        self.learning_log = self.log_dir / "learning_insights.json"
        self.optimization_log = self.log_dir / "optimizations.json"
        self.bug_tracker = self.log_dir / "bug_tracker.json"

        self.conversations = self._load_log(self.today_log, default=[])
        self.learning_insights = self._load_log(self.learning_log, default=[])
        self.optimizations = self._load_log(self.optimization_log, default=[])
        self.bugs = self._load_log(self.bug_tracker, default=[])

    def log_conversation(
        self, user_input: str, assistant_response: str, metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        記錄一次對話

        Args:
            user_input: 用戶輸入
            assistant_response: 助手回應
            metadata: 元數據（標籤、來源等）

        Returns:
            記錄的對話記錄
        """
        conversation = {
            "id": f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.conversations)}",
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "assistant_response": assistant_response,
            "metadata": metadata or {},
            "learning_value": 0.0,
            "extracted_insights": [],
            "quality_score": 0.5,
        }

        # 分析學習價值
        conversation["learning_value"] = self._calculate_learning_value(conversation)
        conversation["extracted_insights"] = self._extract_insights(
            user_input, assistant_response
        )
        conversation["quality_score"] = self._score_quality(conversation)

        self.conversations.append(conversation)
        self._save_log(self.today_log, self.conversations)

        return conversation

    def _calculate_learning_value(self, conversation: Dict) -> float:
        """計算對話的學習價值 (0-1)"""
        value = 0.3  # 基礎值

        response = conversation["assistant_response"]

        # 檢測高價值內容
        high_value_markers = {
            "代碼示例": 0.2,
            "最佳實踐": 0.15,
            "性能優化": 0.15,
            "常見錯誤": 0.15,
            "架構設計": 0.1,
            "安全": 0.1,
        }

        for marker, score in high_value_markers.items():
            if marker in response:
                value += score

        return min(value, 1.0)

    def _extract_insights(self, user_input: str, response: str) -> List[Dict]:
        """從對話中提取洞察"""
        insights = []

        # 檢測問題類型
        if "?" in user_input:
            insights.append(
                {
                    "type": "question_answer",
                    "question": user_input,
                    "has_code": "```" in response,
                    "has_explanation": len(response) > 200,
                }
            )

        # 檢測軟體特徵
        technical_keywords = ["優化", "性能", "修復", "功能", "集成", "部署"]
        for keyword in technical_keywords:
            if keyword in user_input or keyword in response:
                insights.append(
                    {
                        "type": "technical_feature",
                        "keyword": keyword,
                        "context": "mentioned",
                    }
                )

        return insights

    def _score_quality(self, conversation: Dict) -> float:
        """評估對話品質"""
        score = 0.5

        response = conversation["assistant_response"]

        # 長度評分
        if 100 < len(response) < 2000:
            score += 0.2

        # 結構評分
        if response.count("\n") > 3:
            score += 0.15

        # 代碼示例
        if "```" in response:
            score += 0.15

        return min(score, 1.0)

    def record_learning(
        self, source: str, topic: str, learning_item: Dict[str, Any]
    ) -> Dict:
        """
        記錄學習項目

        Args:
            source: 學習來源 (conversation/documentation/etc)
            topic: 主題
            learning_item: 學習內容

        Returns:
            記錄的學習項目
        """
        learning = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "topic": topic,
            "content": learning_item,
            "relevance": 0.5,
            "applied": False,
            "effectiveness": 0.0,
        }

        self.learning_insights.append(learning)
        self._save_log(self.learning_log, self.learning_insights)

        return learning

    def record_optimization(
        self, component: str, change: str, impact: Dict[str, float]
    ) -> Dict:
        """
        記錄系統優化

        Args:
            component: 組件名稱
            change: 變更描述
            impact: 影響指標 (性能、準確度等)

        Returns:
            記錄的優化項目
        """
        optimization = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "change": change,
            "impact": impact,
            "status": "applied",
            "rollback_available": True,
        }

        self.optimizations.append(optimization)
        self._save_log(self.optimization_log, self.optimizations)

        print(f"✅ 優化已記錄: {component} - {change}")
        for metric, value in impact.items():
            symbol = "📈" if value > 0 else "📉"
            print(f"   {symbol} {metric}: {value:+.2%}")

        return optimization

    def report_bug(
        self,
        title: str,
        description: str,
        severity: str = "medium",
        solution: Optional[str] = None,
    ) -> Dict:
        """
        報告 BUG

        Args:
            title: BUG 標題
            description: 詳細描述
            severity: 嚴重性 (low/medium/high/critical)
            solution: 解決方案（可選）

        Returns:
            記錄的 BUG
        """
        bug = {
            "id": f"bug_{len(self.bugs)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "description": description,
            "severity": severity,
            "status": "reported",
            "solution": solution,
            "fixed": False,
        }

        self.bugs.append(bug)
        self._save_log(self.bug_tracker, self.bugs)

        severity_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}

        print(f"{severity_icon.get(severity, '⚪')} BUG 已報告: {title}")
        if solution:
            print(f"   ✅ 解決方案已提供")

        return bug

    def fix_bug(self, bug_id: str, solution_details: str):
        """修復 BUG"""
        for bug in self.bugs:
            if bug["id"] == bug_id:
                bug["fixed"] = True
                bug["status"] = "fixed"
                bug["solution_details"] = solution_details
                bug["fixed_at"] = datetime.now().isoformat()
                print(f"✅ BUG 已修復: {bug_id}")
                break

        self._save_log(self.bug_tracker, self.bugs)

    def get_daily_summary(self) -> Dict[str, Any]:
        """獲取今日摘要"""
        if not self.conversations:
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "conversation_count": 0,
                "total_learning_value": 0,
            }

        summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "conversation_count": len(self.conversations),
            "total_learning_value": sum(
                c.get("learning_value", 0) for c in self.conversations
            ),
            "average_quality": sum(
                c.get("quality_score", 0) for c in self.conversations
            )
            / len(self.conversations)
            if self.conversations
            else 0,
            "insights_extracted": sum(
                len(c.get("extracted_insights", [])) for c in self.conversations
            ),
            "high_value_count": len(
                [c for c in self.conversations if c.get("learning_value", 0) > 0.7]
            ),
        }

        return summary

    def get_optimization_report(self, days: int = 7) -> Dict[str, Any]:
        """獲取優化報告"""
        cutoff = datetime.now().timestamp() - (days * 86400)

        recent_optimizations = [
            o
            for o in self.optimizations
            if datetime.fromisoformat(o["timestamp"]).timestamp() > cutoff
        ]

        report = {
            "period_days": days,
            "optimization_count": len(recent_optimizations),
            "components_improved": list(
                set(o["component"] for o in recent_optimizations)
            ),
            "average_impact": self._calculate_average_impact(recent_optimizations),
            "optimizations": recent_optimizations,
        }

        return report

    def get_bug_report(self) -> Dict[str, Any]:
        """獲取 BUG 報告"""
        total_bugs = len(self.bugs)
        fixed_bugs = len([b for b in self.bugs if b["fixed"]])

        by_severity = defaultdict(int)
        for bug in self.bugs:
            by_severity[bug["severity"]] += 1

        report = {
            "total_bugs": total_bugs,
            "fixed": fixed_bugs,
            "open": total_bugs - fixed_bugs,
            "fix_rate": (fixed_bugs / total_bugs * 100) if total_bugs > 0 else 0,
            "by_severity": dict(by_severity),
            "open_bugs": [b for b in self.bugs if not b["fixed"]],
        }

        return report

    def _calculate_average_impact(self, optimizations: List[Dict]) -> Dict[str, float]:
        """計算平均影響"""
        if not optimizations:
            return {}

        impact_sum = defaultdict(float)
        count = defaultdict(int)

        for opt in optimizations:
            for metric, value in opt.get("impact", {}).items():
                impact_sum[metric] += value
                count[metric] += 1

        return {
            metric: impact_sum[metric] / count[metric] for metric in impact_sum.keys()
        }

    def _load_log(self, path: Path, default: Any = None) -> Any:
        """加載日誌"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default if default is not None else {}

    def _save_log(self, path: Path, data: Any):
        """保存日誌"""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存日誌失敗: {e}")


if __name__ == "__main__":
    # 使用示例
    logger = ConversationLogger()

    # 記錄對話
    conv = logger.log_conversation(
        user_input="如何優化 Python 代碼性能？",
        assistant_response="""最佳實踐:
1. 使用列表推導式
2. 避免全局變數
3. 使用內置函數

代碼示例:
```python
# 優化前
result = []
for i in range(1000000):
    result.append(i * 2)

# 優化後
result = [i * 2 for i in range(1000000)]
```

性能提升: 約 2 倍速度增加""",
    )

    print(f"✅ 對話已記錄")
    print(f"   ID: {conv['id']}")
    print(f"   學習價值: {conv['learning_value']:.2f}")
    print(f"   品質評分: {conv['quality_score']:.2f}")

    # 記錄學習
    learning = logger.record_learning(
        source="conversation",
        topic="Python 優化",
        learning_item={"technique": "列表推導式", "improvement": "性能提升 2 倍"},
    )

    # 記錄優化
    opt = logger.record_optimization(
        component="神經索引",
        change="增加向量維度至 768D",
        impact={"檢索速度": 0.15, "準確度": 0.08},
    )

    # 報告 BUG
    bug = logger.report_bug(
        title="logit 函數語法錯誤",
        description="enhanced_neural_index.py 第 382 行函數定義錯誤",
        severity="high",
        solution="將 'def math.logit' 改為 'def logit'",
    )

    # 修復 BUG
    logger.fix_bug(bug["id"], "已將函數定義改為正確語法")

    # 獲取摘要
    summary = logger.get_daily_summary()
    print(f"\n📊 今日摘要:")
    print(f"   對話數: {summary['conversation_count']}")
    print(f"   學習價值: {summary['total_learning_value']:.2f}")
    print(f"   品質評分: {summary['average_quality']:.2f}")

    # 獲取 BUG 報告
    bug_report = logger.get_bug_report()
    print(f"\n🐛 BUG 報告:")
    print(f"   總計: {bug_report['total_bugs']}")
    print(f"   已修復: {bug_report['fixed']}")
    print(f"   開放: {bug_report['open']}")
    print(f"   修復率: {bug_report['fix_rate']:.1f}%")

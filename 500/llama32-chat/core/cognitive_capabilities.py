#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
進階認知能力系統
實現多種認知模式，提升智能體的推理、學習和決策能力
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class CognitiveResult:
    """認知處理結果"""

    capability_type: str
    input_data: Any
    output_data: Any
    confidence: float
    reasoning: str
    timestamp: str
    metadata: Dict[str, Any] = None


class ReflectiveCapability:
    """反思型能力 - 對過往決策和行為進行反思與評估"""

    def __init__(self):
        self.reflection_history = []

    def reflect_on_decision(
        self, decision: str, outcome: str, context: Dict[str, Any]
    ) -> CognitiveResult:
        """
        反思決策的質量和結果

        Args:
            decision: 所做的決策
            outcome: 決策的結果
            context: 決策時的上下文

        Returns:
            反思結果
        """
        # 分析決策質量
        quality_score = self._evaluate_decision_quality(decision, outcome, context)

        # 提取教訓
        lessons_learned = self._extract_lessons(decision, outcome, context)

        # 生成改進建議
        improvements = self._generate_improvements(decision, outcome, lessons_learned)

        reasoning = f"""
反思分析:
- 決策質量評分: {quality_score}/10
- 關鍵教訓: {", ".join(lessons_learned[:3])}
- 改進方向: {", ".join(improvements[:2])}
"""

        result = CognitiveResult(
            capability_type="reflective",
            input_data={"decision": decision, "outcome": outcome},
            output_data={
                "quality_score": quality_score,
                "lessons_learned": lessons_learned,
                "improvements": improvements,
            },
            confidence=0.8,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context,
        )

        self.reflection_history.append(result)
        return result

    def _evaluate_decision_quality(
        self, decision: str, outcome: str, context: Dict
    ) -> float:
        """評估決策質量（簡化版）"""
        # 基於結果判斷
        if "success" in outcome.lower() or "成功" in outcome:
            return 8.0
        elif "partial" in outcome.lower() or "部分" in outcome:
            return 6.0
        elif "fail" in outcome.lower() or "失敗" in outcome:
            return 3.0
        return 5.0

    def _extract_lessons(self, decision: str, outcome: str, context: Dict) -> List[str]:
        """提取教訓"""
        lessons = []

        if "fail" in outcome.lower() or "失敗" in outcome:
            lessons.append("需要更充分的前期評估")
            lessons.append("應該考慮更多的備選方案")
        else:
            lessons.append("當前策略有效")
            lessons.append("可以作為未來的參考模式")

        return lessons

    def _generate_improvements(
        self, decision: str, outcome: str, lessons: List[str]
    ) -> List[str]:
        """生成改進建議"""
        improvements = []

        if any("評估" in lesson for lesson in lessons):
            improvements.append("增加決策前的風險評估步驟")

        if any("備選" in lesson for lesson in lessons):
            improvements.append("建立備選方案庫")

        improvements.append("記錄決策模式以供學習")

        return improvements


class ChallengeCapability:
    """挑戰型能力 - 質疑假設、尋找反例、測試邊界"""

    def challenge_assumption(
        self, assumption: str, evidence: List[str], context: Dict[str, Any] = None
    ) -> CognitiveResult:
        """
        挑戰某個假設的合理性

        Args:
            assumption: 要挑戰的假設
            evidence: 支持該假設的證據
            context: 上下文信息

        Returns:
            挑戰結果
        """
        # 尋找反例
        counter_examples = self._find_counter_examples(assumption, evidence)

        # 評估假設強度
        strength = self._evaluate_assumption_strength(
            assumption, evidence, counter_examples
        )

        # 提出質疑點
        challenges = self._generate_challenges(assumption, counter_examples)

        reasoning = f"""
挑戰分析:
- 假設強度: {strength}/10
- 發現反例數: {len(counter_examples)}
- 主要質疑: {challenges[0] if challenges else "無明顯漏洞"}
"""

        return CognitiveResult(
            capability_type="challenge",
            input_data={"assumption": assumption, "evidence": evidence},
            output_data={
                "strength": strength,
                "counter_examples": counter_examples,
                "challenges": challenges,
                "should_revise": strength < 5.0,
            },
            confidence=0.7,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context or {},
        )

    def _find_counter_examples(self, assumption: str, evidence: List[str]) -> List[str]:
        """尋找反例"""
        counter_examples = []

        # 簡化實現：基於關鍵詞檢測潛在矛盾
        if "always" in assumption.lower() or "總是" in assumption:
            counter_examples.append("絕對性陳述往往存在例外情況")

        if "never" in assumption.lower() or "從不" in assumption:
            counter_examples.append("否定性陳述需要全面證據支持")

        if len(evidence) < 3:
            counter_examples.append("證據數量不足，可能存在抽樣偏差")

        return counter_examples

    def _evaluate_assumption_strength(
        self, assumption: str, evidence: List[str], counter_examples: List[str]
    ) -> float:
        """評估假設強度"""
        base_strength = 5.0

        # 證據增強
        base_strength += min(len(evidence) * 0.5, 3.0)

        # 反例削弱
        base_strength -= min(len(counter_examples) * 1.0, 4.0)

        return max(1.0, min(10.0, base_strength))

    def _generate_challenges(
        self, assumption: str, counter_examples: List[str]
    ) -> List[str]:
        """生成挑戰性問題"""
        challenges = []

        if counter_examples:
            challenges.append(f"是否考慮了這些反例: {', '.join(counter_examples[:2])}")

        challenges.append("這個假設在極端情況下是否仍然成立？")
        challenges.append("是否有其他解釋可以更好地解釋現象？")

        return challenges


class ConfidenceCalibrationCapability:
    """信心校準型能力 - 評估和校正信心水平"""

    def __init__(self):
        self.calibration_history = []

    def calibrate_confidence(
        self,
        prediction: str,
        initial_confidence: float,
        supporting_factors: List[str],
        uncertainty_factors: List[str],
    ) -> CognitiveResult:
        """
        校準信心水平

        Args:
            prediction: 預測或判斷
            initial_confidence: 初始信心水平 (0-1)
            supporting_factors: 支持因素
            uncertainty_factors: 不確定因素

        Returns:
            校準後的信心結果
        """
        # 計算校準後的信心
        calibrated_confidence = self._calculate_calibrated_confidence(
            initial_confidence, supporting_factors, uncertainty_factors
        )

        # 分析信心來源
        confidence_breakdown = self._analyze_confidence_sources(
            supporting_factors, uncertainty_factors
        )

        # 生成信心報告
        confidence_level = self._get_confidence_level(calibrated_confidence)

        reasoning = f"""
信心校準:
- 初始信心: {initial_confidence:.2%}
- 校準後信心: {calibrated_confidence:.2%}
- 信心等級: {confidence_level}
- 主要不確定性: {uncertainty_factors[0] if uncertainty_factors else "無"}
"""

        result = CognitiveResult(
            capability_type="confidence_calibration",
            input_data={
                "prediction": prediction,
                "initial_confidence": initial_confidence,
            },
            output_data={
                "calibrated_confidence": calibrated_confidence,
                "confidence_level": confidence_level,
                "confidence_breakdown": confidence_breakdown,
                "adjustment": calibrated_confidence - initial_confidence,
            },
            confidence=calibrated_confidence,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
        )

        self.calibration_history.append(result)
        return result

    def _calculate_calibrated_confidence(
        self, initial: float, supporting: List[str], uncertainty: List[str]
    ) -> float:
        """計算校準後的信心"""
        calibrated = initial

        # 支持因素增強（每個+5%，最多+15%）
        support_boost = min(len(supporting) * 0.05, 0.15)
        calibrated += support_boost

        # 不確定因素削弱（每個-8%，最多-25%）
        uncertainty_penalty = min(len(uncertainty) * 0.08, 0.25)
        calibrated -= uncertainty_penalty

        # 過度自信懲罰
        if initial > 0.9:
            calibrated -= 0.1  # 降低過度自信

        return max(0.1, min(0.95, calibrated))

    def _analyze_confidence_sources(
        self, supporting: List[str], uncertainty: List[str]
    ) -> Dict[str, Any]:
        """分析信心來源"""
        return {
            "support_count": len(supporting),
            "uncertainty_count": len(uncertainty),
            "support_ratio": len(supporting) / (len(supporting) + len(uncertainty) + 1),
            "dominant_factor": "supporting"
            if len(supporting) > len(uncertainty)
            else "uncertainty",
        }

    def _get_confidence_level(self, confidence: float) -> str:
        """獲取信心等級描述"""
        if confidence >= 0.85:
            return "非常高"
        elif confidence >= 0.7:
            return "高"
        elif confidence >= 0.5:
            return "中等"
        elif confidence >= 0.3:
            return "低"
        else:
            return "非常低"


class ActiveHypothesisCapability:
    """主動假說型能力 - 主動提出假說並設計驗證方法"""

    def generate_hypotheses(
        self, observation: str, context: Dict[str, Any]
    ) -> CognitiveResult:
        """
        基於觀察生成假說

        Args:
            observation: 觀察到的現象
            context: 上下文信息

        Returns:
            假說生成結果
        """
        # 生成多個假說
        hypotheses = self._brainstorm_hypotheses(observation, context)

        # 為每個假說設計驗證方法
        verification_plans = {}
        for hyp in hypotheses:
            verification_plans[hyp] = self._design_verification(hyp, context)

        # 排序假說（按可行性和影響力）
        ranked_hypotheses = self._rank_hypotheses(hypotheses, verification_plans)

        reasoning = f"""
假說生成:
- 生成假說數: {len(hypotheses)}
- 優先假說: {ranked_hypotheses[0] if ranked_hypotheses else "無"}
- 驗證方法: {verification_plans.get(ranked_hypotheses[0], {}).get("method", "未定義")}
"""

        return CognitiveResult(
            capability_type="active_hypothesis",
            input_data={"observation": observation},
            output_data={
                "hypotheses": hypotheses,
                "ranked_hypotheses": ranked_hypotheses,
                "verification_plans": verification_plans,
            },
            confidence=0.7,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context,
        )

    def _brainstorm_hypotheses(self, observation: str, context: Dict) -> List[str]:
        """頭腦風暴生成假說"""
        hypotheses = []

        # 基於觀察的關鍵詞生成假說
        if "fail" in observation.lower() or "失敗" in observation:
            hypotheses.append("可能是配置錯誤導致")
            hypotheses.append("可能是資源不足引起")
            hypotheses.append("可能是時序問題造成")

        if "slow" in observation.lower() or "慢" in observation:
            hypotheses.append("可能存在性能瓶頸")
            hypotheses.append("可能是網絡延遲影響")

        if "error" in observation.lower() or "錯誤" in observation:
            hypotheses.append("可能是邏輯錯誤")
            hypotheses.append("可能是數據異常")

        # 總是添加一個通用假說
        hypotheses.append("可能需要更多數據來確定原因")

        return hypotheses[:5]  # 最多5個假說

    def _design_verification(self, hypothesis: str, context: Dict) -> Dict[str, Any]:
        """設計驗證方法"""
        verification = {
            "method": "實驗驗證",
            "steps": [],
            "expected_evidence": [],
            "feasibility": 0.7,
        }

        if "配置" in hypothesis:
            verification["steps"] = ["檢查配置文件", "比對標準配置", "測試修改後配置"]
            verification["expected_evidence"] = ["配置差異報告", "測試結果"]
        elif "性能" in hypothesis:
            verification["steps"] = ["性能分析", "瓶頸定位", "優化測試"]
            verification["expected_evidence"] = ["性能分析報告", "優化前後對比"]
        else:
            verification["steps"] = ["收集更多數據", "分析數據模式", "驗證推論"]
            verification["expected_evidence"] = ["數據分析結果"]

        return verification

    def _rank_hypotheses(
        self, hypotheses: List[str], verification_plans: Dict[str, Dict]
    ) -> List[str]:
        """排序假說"""
        # 簡化排序：基於驗證可行性
        scored = []
        for hyp in hypotheses:
            plan = verification_plans.get(hyp, {})
            feasibility = plan.get("feasibility", 0.5)
            scored.append((hyp, feasibility))

        # 按可行性降序排列
        scored.sort(key=lambda x: x[1], reverse=True)
        return [hyp for hyp, _ in scored]


class FailureAnalysisCapability:
    """失敗分析型能力 - 深度分析失敗原因並提取規律"""

    def __init__(self):
        self.failure_database = []

    def analyze_failure(
        self, failure_event: Dict[str, Any], historical_failures: List[Dict] = None
    ) -> CognitiveResult:
        """
        分析失敗事件

        Args:
            failure_event: 失敗事件詳情
            historical_failures: 歷史失敗記錄

        Returns:
            失敗分析結果
        """
        # 分類失敗類型
        failure_type = self._classify_failure(failure_event)

        # 識別根本原因
        root_causes = self._identify_root_causes(failure_event, failure_type)

        # 尋找相似失敗模式
        similar_patterns = self._find_similar_patterns(
            failure_event, historical_failures or self.failure_database
        )

        # 生成防範措施
        preventive_measures = self._generate_preventive_measures(
            root_causes, similar_patterns
        )

        reasoning = f"""
失敗分析:
- 失敗類型: {failure_type}
- 根本原因: {", ".join(root_causes[:2])}
- 相似模式數: {len(similar_patterns)}
- 優先防範: {preventive_measures[0] if preventive_measures else "待定"}
"""

        result = CognitiveResult(
            capability_type="failure_analysis",
            input_data=failure_event,
            output_data={
                "failure_type": failure_type,
                "root_causes": root_causes,
                "similar_patterns": similar_patterns,
                "preventive_measures": preventive_measures,
                "severity": self._assess_severity(failure_event),
            },
            confidence=0.75,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
        )

        self.failure_database.append(result)
        return result

    def _classify_failure(self, event: Dict) -> str:
        """分類失敗類型"""
        error_msg = event.get("error_message", "").lower()

        if "connection" in error_msg or "連接" in error_msg:
            return "連接失敗"
        elif "timeout" in error_msg or "超時" in error_msg:
            return "超時失敗"
        elif "config" in error_msg or "配置" in error_msg:
            return "配置錯誤"
        elif "permission" in error_msg or "權限" in error_msg:
            return "權限問題"
        else:
            return "未知失敗"

    def _identify_root_causes(self, event: Dict, failure_type: str) -> List[str]:
        """識別根本原因"""
        causes = []

        if failure_type == "連接失敗":
            causes.extend(["網絡不穩定", "服務未啟動", "防火牆阻擋"])
        elif failure_type == "超時失敗":
            causes.extend(["處理時間過長", "資源不足", "死鎖"])
        elif failure_type == "配置錯誤":
            causes.extend(["配置文件錯誤", "環境變量缺失", "版本不兼容"])
        else:
            causes.append("需要進一步調查")

        return causes[:3]

    def _find_similar_patterns(self, event: Dict, historical: List[Dict]) -> List[Dict]:
        """尋找相似失敗模式"""
        similar = []
        event_type = event.get("error_type", "")

        for hist in historical[-20:]:  # 只檢查最近20個
            if isinstance(hist, CognitiveResult):
                hist_data = hist.output_data
                if hist_data.get("failure_type") == event_type:
                    similar.append(hist_data)

        return similar[:5]

    def _generate_preventive_measures(
        self, root_causes: List[str], patterns: List[Dict]
    ) -> List[str]:
        """生成防範措施"""
        measures = []

        for cause in root_causes[:2]:
            if "網絡" in cause:
                measures.append("實施網絡重試機制")
            elif "配置" in cause:
                measures.append("添加配置驗證步驟")
            elif "資源" in cause:
                measures.append("增加資源監控和預警")
            elif "權限" in cause:
                measures.append("檢查和更新權限設置")

        if len(patterns) > 3:
            measures.append("建立該類失敗的自動檢測")

        return measures

    def _assess_severity(self, event: Dict) -> str:
        """評估嚴重程度"""
        # 簡化評估
        if event.get("consecutive_failures", 0) > 3:
            return "嚴重"
        elif event.get("impact", "").lower() in ["critical", "嚴重"]:
            return "嚴重"
        elif event.get("error_type") == "config_error":
            return "中等"
        else:
            return "輕微"


class AnalogyTransferCapability:
    """類比遷移型能力 - 從已知領域遷移知識到新領域"""

    def transfer_knowledge(
        self,
        source_domain: str,
        target_domain: str,
        source_solution: str,
        context: Dict[str, Any] = None,
    ) -> CognitiveResult:
        """
        將知識從源領域遷移到目標領域

        Args:
            source_domain: 源領域
            target_domain: 目標領域
            source_solution: 源領域的解決方案
            context: 上下文信息

        Returns:
            知識遷移結果
        """
        # 識別相似性
        similarities = self._identify_similarities(source_domain, target_domain)

        # 適配解決方案
        adapted_solution = self._adapt_solution(
            source_solution, similarities, target_domain
        )

        # 識別潛在陷阱
        pitfalls = self._identify_transfer_pitfalls(
            source_domain, target_domain, similarities
        )

        # 計算遷移可信度
        transferability = self._calculate_transferability(similarities, pitfalls)

        reasoning = f"""
類比遷移:
- 領域相似度: {len(similarities)}/10
- 遷移可信度: {transferability:.2%}
- 關鍵適配: {adapted_solution.get("key_adaptations", ["無"])[0]}
- 主要風險: {pitfalls[0] if pitfalls else "無明顯風險"}
"""

        return CognitiveResult(
            capability_type="analogy_transfer",
            input_data={
                "source_domain": source_domain,
                "target_domain": target_domain,
                "source_solution": source_solution,
            },
            output_data={
                "similarities": similarities,
                "adapted_solution": adapted_solution,
                "pitfalls": pitfalls,
                "transferability": transferability,
            },
            confidence=transferability,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context or {},
        )

    def _identify_similarities(self, source: str, target: str) -> List[str]:
        """識別相似性"""
        similarities = []

        # 簡化實現：基於關鍵詞匹配
        common_keywords = set(source.lower().split()) & set(target.lower().split())

        if common_keywords:
            similarities.append(f"共享關鍵概念: {', '.join(list(common_keywords)[:3])}")

        # 添加一些通用相似性
        similarities.extend(["都涉及系統性問題解決", "都需要資源管理", "都有性能考量"])

        return similarities[:5]

    def _adapt_solution(
        self, solution: str, similarities: List[str], target_domain: str
    ) -> Dict[str, Any]:
        """適配解決方案"""
        return {
            "adapted_approach": f"將 '{solution}' 適配到 {target_domain}",
            "key_adaptations": ["調整參數以適應新環境", "保留核心邏輯", "修改實現細節"],
            "confidence": 0.7 if len(similarities) > 3 else 0.5,
        }

    def _identify_transfer_pitfalls(
        self, source: str, target: str, similarities: List[str]
    ) -> List[str]:
        """識別遷移陷阱"""
        pitfalls = []

        if len(similarities) < 3:
            pitfalls.append("領域差異較大，需謹慎驗證")

        pitfalls.extend(["可能存在隱含假設不適用", "邊界條件可能不同"])

        return pitfalls[:3]

    def _calculate_transferability(
        self, similarities: List[str], pitfalls: List[str]
    ) -> float:
        """計算遷移可信度"""
        base_score = 0.5
        base_score += len(similarities) * 0.08
        base_score -= len(pitfalls) * 0.1

        return max(0.2, min(0.9, base_score))


class ConceptExtractionCapability:
    """概念提取型能力 - 從具體實例中抽象出通用概念"""

    def extract_concepts(
        self, examples: List[Dict[str, Any]], context: Dict[str, Any] = None
    ) -> CognitiveResult:
        """
        從實例中提取概念

        Args:
            examples: 具體實例列表
            context: 上下文信息

        Returns:
            概念提取結果
        """
        # 識別共同模式
        common_patterns = self._identify_common_patterns(examples)

        # 提取核心概念
        core_concepts = self._extract_core_concepts(common_patterns, examples)

        # 建立概念層次
        concept_hierarchy = self._build_concept_hierarchy(core_concepts)

        # 生成概念定義
        concept_definitions = self._generate_definitions(core_concepts, examples)

        reasoning = f"""
概念提取:
- 分析實例數: {len(examples)}
- 提取概念數: {len(core_concepts)}
- 核心概念: {", ".join(core_concepts[:3])}
- 抽象層次: {len(concept_hierarchy)} 層
"""

        return CognitiveResult(
            capability_type="concept_extraction",
            input_data={"examples_count": len(examples)},
            output_data={
                "common_patterns": common_patterns,
                "core_concepts": core_concepts,
                "concept_hierarchy": concept_hierarchy,
                "concept_definitions": concept_definitions,
            },
            confidence=0.75,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context or {},
        )

    def _identify_common_patterns(self, examples: List[Dict]) -> List[str]:
        """識別共同模式"""
        patterns = []

        # 收集所有鍵
        all_keys = set()
        for ex in examples:
            all_keys.update(ex.keys())

        # 找出共同的鍵
        common_keys = all_keys
        for ex in examples:
            common_keys &= set(ex.keys())

        if common_keys:
            patterns.append(f"共同屬性: {', '.join(list(common_keys)[:5])}")

        patterns.append("結構化數據模式")

        return patterns

    def _extract_core_concepts(
        self, patterns: List[str], examples: List[Dict]
    ) -> List[str]:
        """提取核心概念"""
        concepts = []

        # 從模式中提取概念
        for pattern in patterns:
            if "屬性" in pattern:
                concepts.append("數據實體")
            if "結構化" in pattern:
                concepts.append("結構化表示")

        # 從實例中推斷概念
        if examples:
            first_example = examples[0]
            if "error" in str(first_example).lower():
                concepts.append("錯誤處理")
            if (
                "time" in str(first_example).lower()
                or "timestamp" in str(first_example).lower()
            ):
                concepts.append("時序事件")

        concepts.append("通用模式")

        return list(set(concepts))[:5]

    def _build_concept_hierarchy(self, concepts: List[str]) -> Dict[str, List[str]]:
        """建立概念層次"""
        hierarchy = {
            "頂層概念": ["系統行為"],
            "中層概念": concepts,
            "底層概念": ["具體實現細節"],
        }
        return hierarchy

    def _generate_definitions(
        self, concepts: List[str], examples: List[Dict]
    ) -> Dict[str, str]:
        """生成概念定義"""
        definitions = {}

        for concept in concepts:
            definitions[concept] = (
                f"{concept}: 從 {len(examples)} 個實例中抽象出的通用模式"
            )

        return definitions


class QueryProcessingCapability:
    """查詢處理型能力 - 處理多種類型的查詢（時效性、缺口填補、驗證式、分解式）"""

    def process_temporal_query(
        self, query: str, time_context: Dict[str, Any]
    ) -> CognitiveResult:
        """
        處理時效性查詢

        Args:
            query: 查詢內容
            time_context: 時間上下文（包含當前時間、數據時間範圍等）

        Returns:
            查詢處理結果
        """
        # 識別時間約束
        time_constraints = self._extract_time_constraints(query)

        # 評估數據時效性
        data_freshness = self._assess_data_freshness(time_context)

        # 生成時效性報告
        temporal_report = {
            "is_time_sensitive": bool(time_constraints),
            "time_constraints": time_constraints,
            "data_freshness": data_freshness,
            "requires_update": data_freshness < 0.5,
        }

        reasoning = f"""
時效性查詢:
- 時間敏感度: {"高" if temporal_report["is_time_sensitive"] else "低"}
- 數據新鮮度: {data_freshness:.2%}
- 是否需更新: {"是" if temporal_report["requires_update"] else "否"}
"""

        return CognitiveResult(
            capability_type="temporal_query",
            input_data={"query": query},
            output_data=temporal_report,
            confidence=0.8,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=time_context,
        )

    def process_gap_filling_query(
        self, known_data: Dict[str, Any], missing_fields: List[str]
    ) -> CognitiveResult:
        """
        處理缺口填補型查詢

        Args:
            known_data: 已知數據
            missing_fields: 缺失字段

        Returns:
            缺口填補結果
        """
        # 推斷缺失值
        inferred_values = self._infer_missing_values(known_data, missing_fields)

        # 評估推斷可信度
        inference_confidence = self._assess_inference_confidence(
            known_data, inferred_values
        )

        # 識別需要額外信息的字段
        needs_more_info = [
            field for field, conf in inference_confidence.items() if conf < 0.5
        ]

        reasoning = f"""
缺口填補:
- 缺失字段數: {len(missing_fields)}
- 成功推斷數: {len(inferred_values)}
- 需更多信息: {len(needs_more_info)}
"""

        return CognitiveResult(
            capability_type="gap_filling",
            input_data={"known_fields": list(known_data.keys())},
            output_data={
                "inferred_values": inferred_values,
                "inference_confidence": inference_confidence,
                "needs_more_info": needs_more_info,
            },
            confidence=sum(inference_confidence.values()) / len(inference_confidence)
            if inference_confidence
            else 0.5,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
        )

    def process_verification_query(
        self, claim: str, evidence: List[str], context: Dict[str, Any] = None
    ) -> CognitiveResult:
        """
        處理驗證式查詢

        Args:
            claim: 待驗證的聲明
            evidence: 證據列表
            context: 上下文

        Returns:
            驗證結果
        """
        # 評估證據支持度
        support_score = self._evaluate_evidence_support(claim, evidence)

        # 識別矛盾證據
        contradictions = self._find_contradictions(claim, evidence)

        # 生成驗證結論
        verification_result = {
            "is_verified": support_score > 0.7 and len(contradictions) == 0,
            "support_score": support_score,
            "contradictions": contradictions,
            "confidence_level": self._get_verification_confidence(
                support_score, contradictions
            ),
        }

        reasoning = f"""
驗證查詢:
- 聲明: {claim[:50]}...
- 證據數量: {len(evidence)}
- 支持度: {support_score:.2%}
- 驗證結果: {"通過" if verification_result["is_verified"] else "未通過"}
"""

        return CognitiveResult(
            capability_type="verification",
            input_data={"claim": claim, "evidence_count": len(evidence)},
            output_data=verification_result,
            confidence=verification_result["confidence_level"],
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context or {},
        )

    def process_decomposition_query(
        self, complex_query: str, context: Dict[str, Any] = None
    ) -> CognitiveResult:
        """
        處理分解式查詢 - 將複雜查詢分解為子問題

        Args:
            complex_query: 複雜查詢
            context: 上下文

        Returns:
            分解結果
        """
        # 識別查詢組件
        query_components = self._identify_query_components(complex_query)

        # 分解為子問題
        sub_queries = self._decompose_into_subqueries(complex_query, query_components)

        # 建立依賴關係
        dependencies = self._establish_dependencies(sub_queries)

        # 生成執行計劃
        execution_plan = self._generate_execution_plan(sub_queries, dependencies)

        reasoning = f"""
分解查詢:
- 原始查詢複雜度: {len(complex_query.split())} 詞
- 分解子問題數: {len(sub_queries)}
- 執行步驟數: {len(execution_plan)}
"""

        return CognitiveResult(
            capability_type="decomposition",
            input_data={"complex_query": complex_query},
            output_data={
                "query_components": query_components,
                "sub_queries": sub_queries,
                "dependencies": dependencies,
                "execution_plan": execution_plan,
            },
            confidence=0.8,
            reasoning=reasoning.strip(),
            timestamp=datetime.now().isoformat(),
            metadata=context or {},
        )

    # 輔助方法

    def _extract_time_constraints(self, query: str) -> List[str]:
        """提取時間約束"""
        time_keywords = [
            "最新",
            "最近",
            "今天",
            "yesterday",
            "last week",
            "recent",
            "latest",
        ]
        constraints = []

        query_lower = query.lower()
        for keyword in time_keywords:
            if keyword in query_lower:
                constraints.append(keyword)

        return constraints

    def _assess_data_freshness(self, time_context: Dict) -> float:
        """評估數據新鮮度"""
        # 簡化實現
        last_update = time_context.get("last_update")
        if not last_update:
            return 0.5

        # 假設數據在24小時內是新鮮的
        return 0.9  # 簡化為固定值

    def _infer_missing_values(
        self, known_data: Dict, missing_fields: List[str]
    ) -> Dict[str, Any]:
        """推斷缺失值"""
        inferred = {}

        for field in missing_fields:
            # 簡化推斷邏輯
            if "time" in field.lower():
                inferred[field] = datetime.now().isoformat()
            elif "count" in field.lower():
                inferred[field] = 0
            elif "status" in field.lower():
                inferred[field] = "unknown"
            else:
                inferred[field] = None

        return inferred

    def _assess_inference_confidence(
        self, known_data: Dict, inferred: Dict
    ) -> Dict[str, float]:
        """評估推斷可信度"""
        confidence = {}

        for field, value in inferred.items():
            if value is None:
                confidence[field] = 0.1
            elif "time" in field.lower():
                confidence[field] = 0.6
            else:
                confidence[field] = 0.5

        return confidence

    def _evaluate_evidence_support(self, claim: str, evidence: List[str]) -> float:
        """評估證據支持度"""
        if not evidence:
            return 0.0

        # 簡化：基於證據數量
        base_score = min(len(evidence) * 0.2, 0.8)

        # 檢查證據相關性
        claim_keywords = set(claim.lower().split())
        relevant_evidence = 0

        for ev in evidence:
            ev_keywords = set(ev.lower().split())
            if claim_keywords & ev_keywords:
                relevant_evidence += 1

        relevance_boost = (relevant_evidence / len(evidence)) * 0.2

        return min(base_score + relevance_boost, 0.95)

    def _find_contradictions(self, claim: str, evidence: List[str]) -> List[str]:
        """尋找矛盾證據"""
        contradictions = []

        # 簡化檢測
        claim_lower = claim.lower()

        for ev in evidence:
            ev_lower = ev.lower()
            if (
                "not" in ev_lower or "沒有" in ev_lower
            ) and claim_lower not in ev_lower:
                contradictions.append(ev[:100])

        return contradictions

    def _get_verification_confidence(
        self, support_score: float, contradictions: List[str]
    ) -> float:
        """獲取驗證可信度"""
        confidence = support_score

        # 矛盾降低可信度
        confidence -= len(contradictions) * 0.2

        return max(0.1, min(0.95, confidence))

    def _identify_query_components(self, query: str) -> List[str]:
        """識別查詢組件"""
        components = []

        # 基於連接詞分割
        connectors = [" and ", " or ", " then ", " 並且 ", " 或者 ", " 然後 "]

        parts = [query]
        for connector in connectors:
            new_parts = []
            for part in parts:
                new_parts.extend(part.split(connector))
            parts = new_parts

        return [p.strip() for p in parts if p.strip()]

    def _decompose_into_subqueries(
        self, query: str, components: List[str]
    ) -> List[Dict[str, str]]:
        """分解為子查詢"""
        sub_queries = []

        for i, component in enumerate(components):
            sub_queries.append(
                {"id": f"sub_query_{i + 1}", "query": component, "priority": i + 1}
            )

        return sub_queries

    def _establish_dependencies(self, sub_queries: List[Dict]) -> Dict[str, List[str]]:
        """建立依賴關係"""
        dependencies = {}

        # 簡化：順序依賴
        for i, sq in enumerate(sub_queries):
            if i > 0:
                dependencies[sq["id"]] = [sub_queries[i - 1]["id"]]
            else:
                dependencies[sq["id"]] = []

        return dependencies

    def _generate_execution_plan(
        self, sub_queries: List[Dict], dependencies: Dict
    ) -> List[Dict[str, Any]]:
        """生成執行計劃"""
        plan = []

        for sq in sub_queries:
            plan.append(
                {
                    "step": len(plan) + 1,
                    "query_id": sq["id"],
                    "query": sq["query"],
                    "depends_on": dependencies.get(sq["id"], []),
                    "estimated_time": "快速" if len(sq["query"]) < 50 else "中等",
                }
            )

        return plan


class CognitiveCapabilityManager:
    """認知能力管理器 - 統一管理所有認知能力"""

    def __init__(self):
        self.reflective = ReflectiveCapability()
        self.challenge = ChallengeCapability()
        self.confidence_calibration = ConfidenceCalibrationCapability()
        self.active_hypothesis = ActiveHypothesisCapability()
        self.failure_analysis = FailureAnalysisCapability()
        self.analogy_transfer = AnalogyTransferCapability()
        self.concept_extraction = ConceptExtractionCapability()
        self.query_processing = QueryProcessingCapability()

        self.capability_log = []

    def get_capability(self, capability_name: str):
        """獲取特定認知能力"""
        capability_map = {
            "reflective": self.reflective,
            "challenge": self.challenge,
            "confidence_calibration": self.confidence_calibration,
            "active_hypothesis": self.active_hypothesis,
            "failure_analysis": self.failure_analysis,
            "analogy_transfer": self.analogy_transfer,
            "concept_extraction": self.concept_extraction,
            "query_processing": self.query_processing,
        }
        return capability_map.get(capability_name)

    def log_capability_usage(self, result: CognitiveResult):
        """記錄認知能力使用情況"""
        self.capability_log.append(
            {
                "capability": result.capability_type,
                "timestamp": result.timestamp,
                "confidence": result.confidence,
            }
        )

    def get_usage_statistics(self) -> Dict[str, Any]:
        """獲取使用統計"""
        if not self.capability_log:
            return {"message": "尚無使用記錄"}

        stats = {}
        for entry in self.capability_log:
            cap = entry["capability"]
            if cap not in stats:
                stats[cap] = {"count": 0, "avg_confidence": 0.0, "confidences": []}

            stats[cap]["count"] += 1
            stats[cap]["confidences"].append(entry["confidence"])

        # 計算平均信心度
        for cap, data in stats.items():
            data["avg_confidence"] = sum(data["confidences"]) / len(data["confidences"])
            del data["confidences"]  # 移除原始列表

        return stats


# 全局認知能力管理器實例
cognitive_manager = CognitiveCapabilityManager()


if __name__ == "__main__":
    print("🧠 進階認知能力系統測試\n")

    # 測試反思能力
    print("=" * 60)
    print("1. 測試反思型能力")
    print("=" * 60)
    reflective = ReflectiveCapability()
    result = reflective.reflect_on_decision(
        decision="選擇使用快取來提升性能",
        outcome="成功減少了50%的響應時間",
        context={"system": "chat_system"},
    )
    print(result.reasoning)
    print(f"信心度: {result.confidence}")

    # 測試挑戰能力
    print("\n" + "=" * 60)
    print("2. 測試挑戰型能力")
    print("=" * 60)
    challenge = ChallengeCapability()
    result = challenge.challenge_assumption(
        assumption="所有用戶總是偏好更快的響應速度",
        evidence=["用戶調查顯示80%用戶選擇速度", "性能測試證實更快"],
        context={},
    )
    print(result.reasoning)

    # 測試信心校準
    print("\n" + "=" * 60)
    print("3. 測試信心校準型能力")
    print("=" * 60)
    calibration = ConfidenceCalibrationCapability()
    result = calibration.calibrate_confidence(
        prediction="系統在高負載下仍能保持穩定",
        initial_confidence=0.9,
        supporting_factors=["已通過壓力測試", "有冗餘設計"],
        uncertainty_factors=["未測試極端情況", "依賴第三方服務"],
    )
    print(result.reasoning)

    # 測試失敗分析
    print("\n" + "=" * 60)
    print("4. 測試失敗分析型能力")
    print("=" * 60)
    failure_analysis = FailureAnalysisCapability()
    result = failure_analysis.analyze_failure(
        failure_event={
            "error_message": "Connection timeout after 30 seconds",
            "error_type": "timeout_error",
            "consecutive_failures": 3,
        }
    )
    print(result.reasoning)

    # 測試查詢分解
    print("\n" + "=" * 60)
    print("5. 測試分解式查詢能力")
    print("=" * 60)
    query_proc = QueryProcessingCapability()
    result = query_proc.process_decomposition_query(
        complex_query="分析最近7天的系統性能並生成報告，然後發送給管理員"
    )
    print(result.reasoning)
    print(f"\n執行計劃:")
    for step in result.output_data["execution_plan"]:
        print(f"  步驟 {step['step']}: {step['query']}")

    print("\n✅ 所有認知能力測試完成")

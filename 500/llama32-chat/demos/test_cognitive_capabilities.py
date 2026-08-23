#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
進階認知能力系統測試腳本
演示所有認知能力的使用方法
"""

import sys
from pathlib import Path

# 添加父目錄到路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.autonomous_agent import autonomous_agent


def print_section(title):
    """打印章節標題"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_reflective_capability():
    """測試反思型能力"""
    print_section("1. 反思型能力測試")

    # 測試成功案例的反思
    result = autonomous_agent.reflect_on_decision(
        decision="選擇使用本地 Ollama 模型處理簡單對話",
        outcome="成功：響應時間快，準確度高",
        context={"task_type": "conversation", "model": "ollama"},
    )

    print(f"\n決策反思結果:")
    print(f"  質量評分: {result.get('quality_score', 'N/A')}/10")
    print(f"  關鍵教訓:")
    for lesson in result.get("lessons_learned", [])[:3]:
        print(f"    - {lesson}")
    print(f"  改進建議:")
    for improvement in result.get("improvements", [])[:3]:
        print(f"    - {improvement}")
    print(f"  信心度: {result.get('confidence', 0):.2%}")

    # 測試失敗案例的反思
    result2 = autonomous_agent.reflect_on_decision(
        decision="在網絡不穩定時選擇使用遠程 API",
        outcome="失敗：連接超時，多次重試",
        context={"task_type": "code", "model": "openai"},
    )

    print(f"\n失敗案例反思:")
    print(f"  質量評分: {result2.get('quality_score', 'N/A')}/10")
    print(f"  關鍵教訓:")
    for lesson in result2.get("lessons_learned", [])[:3]:
        print(f"    - {lesson}")


def test_challenge_capability():
    """測試挑戰型能力"""
    print_section("2. 挑戰型能力測試")

    result = autonomous_agent.challenge_assumption(
        assumption="所有用戶總是偏好最快的響應速度",
        evidence=[
            "用戶調查顯示 80% 選擇速度優先",
            "性能測試顯示快速響應帶來更高滿意度",
        ],
        context={"domain": "user_experience"},
    )

    print(f"\n假設挑戰結果:")
    print(f"  假設強度: {result.get('strength', 'N/A')}/10")
    print(f"  反例數量: {len(result.get('counter_examples', []))}")
    print(f"  主要反例:")
    for example in result.get("counter_examples", [])[:3]:
        print(f"    - {example}")
    print(f"  需要修正: {'是' if result.get('should_revise') else '否'}")
    print(f"  挑戰性問題:")
    for challenge in result.get("challenges", [])[:2]:
        print(f"    - {challenge}")


def test_confidence_calibration():
    """測試信心校準能力"""
    print_section("3. 信心校準型能力測試")

    result = autonomous_agent.calibrate_confidence(
        prediction="新功能將在一週內完成",
        initial_confidence=0.9,
        supporting_factors=["團隊經驗豐富", "需求明確", "有類似案例"],
        uncertainty_factors=["依賴第三方 API", "未測試所有場景", "可能有隱藏需求"],
    )

    print(f"\n信心校準結果:")
    print(f"  初始信心: {result.get('initial_confidence', 0):.2%}")
    print(f"  校準後信心: {result.get('calibrated_confidence', 0):.2%}")
    print(f"  信心等級: {result.get('confidence_level', 'N/A')}")
    print(f"  調整幅度: {result.get('adjustment', 0):+.2%}")
    print(f"\n推理過程:")
    print(f"  {result.get('reasoning', '')}")


def test_hypothesis_generation():
    """測試主動假說能力"""
    print_section("4. 主動假說型能力測試")

    result = autonomous_agent.generate_hypotheses(
        observation="系統在高峰時段出現間歇性響應緩慢",
        context={
            "system": "chat_api",
            "peak_hours": "18:00-21:00",
            "normal_response_time": "200ms",
            "slow_response_time": "2000ms",
        },
    )

    print(f"\n假說生成結果:")
    print(f"  生成假說數: {len(result.get('hypotheses', []))}")
    print(f"  優先假說:")
    for i, hyp in enumerate(result.get("ranked_hypotheses", [])[:3], 1):
        print(f"    {i}. {hyp}")

    if result.get("verification_plans"):
        top_hypothesis = result.get("ranked_hypotheses", [""])[0]
        plan = result.get("verification_plans", {}).get(top_hypothesis, {})
        print(f"\n  優先假說的驗證計劃:")
        print(f"    方法: {plan.get('method', 'N/A')}")
        print(f"    步驟:")
        for step in plan.get("steps", [])[:3]:
            print(f"      - {step}")


def test_failure_analysis():
    """測試失敗分析能力"""
    print_section("5. 失敗分析型能力測試")

    failure_event = {
        "model": "openai",
        "error_message": "Connection timeout: Failed to connect to api.openai.com after 30 seconds",
        "error_type": "timeout_error",
        "timestamp": "2026-04-16T10:30:00",
        "consecutive_failures": 3,
        "impact": "medium",
    }

    result = autonomous_agent.analyze_failure_with_cognition(
        failure_event=failure_event, historical_failures=[]
    )

    print(f"\n失敗分析結果:")
    print(f"  失敗類型: {result.get('failure_type', 'N/A')}")
    print(f"  嚴重程度: {result.get('severity', 'N/A')}")
    print(f"  根本原因:")
    for cause in result.get("root_causes", [])[:3]:
        print(f"    - {cause}")
    print(f"  防範措施:")
    for measure in result.get("preventive_measures", [])[:3]:
        print(f"    - {measure}")
    print(f"  相似模式數: {len(result.get('similar_patterns', []))}")


def test_knowledge_transfer():
    """測試類比遷移能力"""
    print_section("6. 類比遷移型能力測試")

    result = autonomous_agent.transfer_knowledge(
        source_domain="Web 應用快取策略",
        target_domain="AI 模型響應快取",
        source_solution="使用 Redis 作為分散式快取，設置合理的 TTL",
        context={"source_scale": "high_traffic_web", "target_scale": "moderate_ai_api"},
    )

    print(f"\n知識遷移結果:")
    print(f"  遷移可信度: {result.get('transferability', 0):.2%}")
    print(f"  識別的相似性:")
    for sim in result.get("similarities", [])[:4]:
        print(f"    - {sim}")
    print(f"  適配方案:")
    adapted = result.get("adapted_solution", {})
    print(f"    {adapted.get('adapted_approach', 'N/A')}")
    print(f"  關鍵適配:")
    for adapt in adapted.get("key_adaptations", [])[:3]:
        print(f"    - {adapt}")
    print(f"  潛在陷阱:")
    for pitfall in result.get("pitfalls", [])[:3]:
        print(f"    - {pitfall}")


def test_concept_extraction():
    """測試概念提取能力"""
    print_section("7. 概念提取型能力測試")

    examples = [
        {"type": "timeout_error", "retry_count": 3, "success": False, "duration": 30},
        {
            "type": "connection_error",
            "retry_count": 2,
            "success": False,
            "duration": 15,
        },
        {"type": "timeout_error", "retry_count": 1, "success": True, "duration": 35},
        {"type": "api_error", "retry_count": 0, "success": False, "duration": 5},
    ]

    result = autonomous_agent.extract_concepts(
        examples=examples, context={"domain": "error_handling"}
    )

    print(f"\n概念提取結果:")
    print(f"  分析實例數: {len(examples)}")
    print(f"  共同模式:")
    for pattern in result.get("common_patterns", []):
        print(f"    - {pattern}")
    print(f"  核心概念:")
    for concept in result.get("core_concepts", []):
        print(f"    - {concept}")
    print(f"  概念層次:")
    hierarchy = result.get("concept_hierarchy", {})
    for level, concepts in hierarchy.items():
        print(f"    {level}: {', '.join(concepts[:3])}")


def test_query_processing():
    """測試查詢處理能力"""
    print_section("8. 查詢處理型能力測試")

    # 8.1 時效性查詢
    print("\n8.1 時效性查詢")
    result = autonomous_agent.process_temporal_query(
        query="獲取最近24小時內的系統錯誤",
        time_context={
            "current_time": "2026-04-16T12:00:00",
            "last_update": "2026-04-16T11:50:00",
            "data_range": "past_7_days",
        },
    )
    print(f"  時間敏感: {'是' if result.get('is_time_sensitive') else '否'}")
    print(f"  數據新鮮度: {result.get('data_freshness', 0):.2%}")
    print(f"  需要更新: {'是' if result.get('requires_update') else '否'}")

    # 8.2 缺口填補查詢
    print("\n8.2 缺口填補查詢")
    result = autonomous_agent.process_gap_filling_query(
        known_data={"model": "ollama", "error_type": "timeout"},
        missing_fields=["timestamp", "retry_count", "status"],
    )
    print(f"  推斷值:")
    for field, value in result.get("inferred_values", {}).items():
        conf = result.get("inference_confidence", {}).get(field, 0)
        print(f"    {field}: {value} (信心度: {conf:.2%})")

    # 8.3 驗證式查詢
    print("\n8.3 驗證式查詢")
    result = autonomous_agent.process_verification_query(
        claim="Ollama 模型適合處理簡單對話任務",
        evidence=[
            "本地運行速度快",
            "無需網絡連接",
            "適合處理常見問題",
            "在複雜推理任務上表現有限",
        ],
    )
    print(f"  驗證結果: {'通過' if result.get('is_verified') else '未通過'}")
    print(f"  支持度: {result.get('support_score', 0):.2%}")
    print(f"  信心等級: {result.get('confidence_level', 0):.2%}")

    # 8.4 分解式查詢
    print("\n8.4 分解式查詢")
    result = autonomous_agent.process_decomposition_query(
        complex_query="分析過去7天的系統性能，生成報告，並發送給管理員和優化建議"
    )
    print(f"  分解子問題數: {len(result.get('sub_queries', []))}")
    print(f"  執行計劃:")
    for step in result.get("execution_plan", []):
        print(f"    步驟 {step.get('step')}: {step.get('query')}")
        if step.get("depends_on"):
            print(f"      依賴: {', '.join(step.get('depends_on'))}")


def test_cognitive_statistics():
    """測試認知能力使用統計"""
    print_section("9. 認知能力使用統計")

    stats = autonomous_agent.get_cognitive_usage_statistics()

    if "message" in stats:
        print(f"\n  {stats['message']}")
    else:
        print(f"\n  認知能力使用摘要:")
        for capability, data in stats.items():
            print(f"\n  {capability}:")
            print(f"    使用次數: {data.get('count', 0)}")
            print(f"    平均信心度: {data.get('avg_confidence', 0):.2%}")


def main():
    """主測試函數"""
    print("\n" + "=" * 70)
    print("  🧠 進階認知能力系統 - 全面測試")
    print("=" * 70)

    # 檢查認知能力系統是否可用
    if not autonomous_agent.cognitive_manager:
        print("\n❌ 認知能力系統未初始化")
        print("   請確保 cognitive_capabilities.py 已正確導入")
        return

    print("\n✅ 認知能力系統已就緒，開始測試...\n")

    try:
        # 執行所有測試
        test_reflective_capability()
        test_challenge_capability()
        test_confidence_calibration()
        test_hypothesis_generation()
        test_failure_analysis()
        test_knowledge_transfer()
        test_concept_extraction()
        test_query_processing()
        test_cognitive_statistics()

        print("\n" + "=" * 70)
        print("  ✅ 所有認知能力測試完成")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 測試過程中發生錯誤: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

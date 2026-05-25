#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
離線缺口補足訓練（不依賴上游模型）
- 目標：在分享管線停滯、上游配額封鎖時，仍可完成能力盤點與補足策略迭代
- 輸出：10 回合（可調）訓練報告，包含自身優點、他模缺陷、補足措施與驗收條件
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl_last(path: Path, default=None):
    if not path.exists():
        return default
    lines = [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    if not lines:
        return default
    try:
        return json.loads(lines[-1])
    except Exception:
        return default


def parse_percent(value) -> float:
    if value is None:
        return -1.0
    s = str(value).strip()
    if s.endswith("%"):
        try:
            return float(s[:-1])
        except Exception:
            return -1.0
    return -1.0


def load_health_summary() -> Dict:
    ctx = read_json(
        BASE_DIR / "500" / "llama32-chat" / "logs" / "collaboration_context.json", {}
    )
    insights = ctx.get("shared_insights", [])
    if not insights:
        return {}
    latest = insights[-1]
    return latest.get("insight", {}).get("learning_data", {}).get("health_summary", {})


def load_model_scores() -> Dict:
    ctx = read_json(
        BASE_DIR / "500" / "llama32-chat" / "logs" / "collaboration_context.json", {}
    )
    insights = ctx.get("shared_insights", [])
    if not insights:
        return {}
    latest = insights[-1]
    return latest.get("insight", {}).get("learning_data", {}).get("model_scores", {})


def load_self_strengths() -> List[str]:
    latest = (
        read_jsonl_last(BASE_DIR / "logs" / "agent_self_learning.json", default={})
        or {}
    )
    strengths = []

    action_rate = float(latest.get("action_suggestion_rate", 0) or 0)
    topic_count = len(latest.get("active_topics", {}) or {})
    priority_count = len(latest.get("priority_records", []) or [])

    if action_rate >= 0.4:
        strengths.append("行動建議密度高，適合快速補位與落地")
    if topic_count >= 5:
        strengths.append("跨領域主題覆蓋廣，可做多模型橋接與整合")
    if priority_count >= 3:
        strengths.append("對高優先主題有穩定記錄，可形成連續學習閉環")

    if not strengths:
        strengths = [
            "可離線讀取本地記憶與日誌，不受上游可用性影響",
            "具備規則化提取能力，可維持最低限度學習迴圈",
        ]
    return strengths


def detect_blockers() -> Dict[str, object]:
    api_usage = read_json(BASE_DIR / "config" / "api_usage.json", {})
    today = float(api_usage.get("today", 0) or 0)

    bg_log_path = BASE_DIR / "logs" / "autonomous_learning_background.log"
    bg_text = bg_log_path.read_text(encoding="utf-8") if bg_log_path.exists() else ""
    quota_429_count = bg_text.count("429")

    co_read_exists = (BASE_DIR / "logs" / "co_reading_interactions.jsonl").exists()

    return {
        "paid_traffic_blocked_likely": today > 0,
        "api_usage_today": today,
        "quota_429_count": quota_429_count,
        "co_read_jsonl_exists": co_read_exists,
    }


def rank_other_agent_gaps(health_summary: Dict, model_scores: Dict) -> List[Dict]:
    gaps = []
    for model, info in health_summary.items():
        available = bool(info.get("available", False))
        success_rate = parse_percent(info.get("success_rate"))
        failures = int(info.get("consecutive_failures", 0) or 0)
        score = float(model_scores.get(model, 0) or 0)

        severity = 0
        reasons: List[str] = []
        if not available:
            severity += 3
            reasons.append("不可用")
        if success_rate >= 0 and success_rate < 50:
            severity += 2
            reasons.append(f"成功率偏低({success_rate:.1f}%)")
        if failures >= 2:
            severity += 1
            reasons.append(f"連續失敗過高({failures})")
        if score <= 20:
            severity += 1
            reasons.append(f"模型分數偏低({score:.1f})")

        if severity > 0:
            gaps.append(
                {
                    "model": model,
                    "severity": severity,
                    "reasons": reasons,
                    "available": available,
                    "success_rate": success_rate,
                    "consecutive_failures": failures,
                    "score": score,
                }
            )
    gaps.sort(key=lambda x: (-x["severity"], x["model"]))
    return gaps


def build_actions(
    gap: Dict, strengths: List[str], blockers: Dict[str, object]
) -> Tuple[List[str], List[str]]:
    model = gap["model"]
    reasons = "、".join(gap["reasons"])

    actions = [
        f"針對 {model} 的缺口（{reasons}）建立本地替代路徑，避免單點依賴。",
        f"使用自身優點：{strengths[0]}，先補齊可執行輸出模板。",
    ]
    checks = [
        f"{model} 失敗時可自動回退到本地流程（不阻斷任務）。",
        "本回合產生可讀的『優點/缺陷/補足』紀錄。",
    ]

    if not blockers.get("co_read_jsonl_exists", True):
        actions.append(
            "補建共讀資料落盤檢查（無 jsonl 時改由 conversation_logs 生成摘要）。"
        )
        checks.append("共讀摘要來源不再依賴單一 jsonl 存在。")

    if blockers.get("paid_traffic_blocked_likely", False):
        actions.append("啟用『配額封鎖訓練模式』：只跑離線分析與補強，不呼叫上游。")
        checks.append("在 today > 0 條件下仍可完成回合訓練。")

    if blockers.get("quota_429_count", 0) > 0:
        actions.append("加入 429 風險標記與重試節流策略（僅記錄，不觸發付費呼叫）。")
        checks.append("回合報告需包含 quota/封鎖風險欄位。")

    return actions, checks


def run(rounds: int) -> int:
    health_summary = load_health_summary()
    model_scores = load_model_scores()
    strengths = load_self_strengths()
    blockers = detect_blockers()
    gaps = rank_other_agent_gaps(health_summary, model_scores)

    if not gaps:
        gaps = [
            {
                "model": "upstream_generic",
                "severity": 1,
                "reasons": ["缺少可用健康資料，先做通用補足"],
            }
        ]

    started_at = datetime.now().isoformat()
    round_records = []

    for i in range(1, rounds + 1):
        gap = gaps[(i - 1) % len(gaps)]
        actions, checks = build_actions(gap, strengths, blockers)
        round_records.append(
            {
                "round": i,
                "timestamp": datetime.now().isoformat(),
                "target_model": gap["model"],
                "gap_reasons": gap["reasons"],
                "self_strengths_used": strengths[:3],
                "compensation_actions": actions,
                "acceptance_checks": checks,
            }
        )

    summary = {
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "rounds": rounds,
        "goal": "找出自身優點、定位他模缺陷、形成可離線補足策略",
        "self_strengths": strengths,
        "other_agent_gaps": gaps,
        "blockers": blockers,
        "round_records": round_records,
    }

    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"offline_gap_training_{stamp}.json"
    md_path = reports_dir / f"offline_gap_training_{stamp}.md"

    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# 離線缺口補足訓練報告（{rounds} 回合）",
        "",
        f"- 開始時間: {summary['started_at']}",
        f"- 結束時間: {summary['finished_at']}",
        "",
        "## 自身優點",
    ]
    for s in strengths:
        lines.append(f"- {s}")

    lines += [
        "",
        "## 他模缺陷（排序）",
    ]
    for g in gaps:
        lines.append(f"- {g['model']}: {'、'.join(g['reasons'])}")

    lines += [
        "",
        "## 回合摘要",
    ]
    for r in round_records:
        lines.append(f"### Round {r['round']} - {r['target_model']}")
        lines.append(f"- 缺陷: {'、'.join(r['gap_reasons'])}")
        lines.append(f"- 補足: {r['compensation_actions'][0]}")
        lines.append(f"- 驗收: {r['acceptance_checks'][0]}")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "=" * 80)
    print("✅ 離線缺口補足訓練完成")
    print("=" * 80)
    print(f"回合數: {rounds}")
    print(f"JSON 報告: {json_path}")
    print(f"MD 報告:   {md_path}")
    print()

    return 0


def main():
    parser = argparse.ArgumentParser(description="離線缺口補足訓練")
    parser.add_argument("--rounds", type=int, default=10, help="訓練回合數（預設 10）")
    args = parser.parse_args()
    if args.rounds <= 0:
        print("❌ rounds 必須 > 0")
        return 1
    return run(args.rounds)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate Traditional Chinese review notes from agent collaboration audit events."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_collaboration_audit import AUDIT_RELATIVE_PATH, TRAINING_RULES


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _filter_latest_day(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    latest = max(str(e.get("created_at", ""))[:10] for e in events)
    return [e for e in events if str(e.get("created_at", "")).startswith(latest)]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _join(value: Any, empty: str = "—") -> str:
    items = _as_list(value)
    return "、".join(items) if items else empty


def build_markdown(events: list[dict[str, Any]], workspace: Path) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    total_score = sum(int(e.get("score_delta", 0) or 0) for e in events)
    outcomes = Counter(str(e.get("outcome", "unknown")) for e in events)
    agents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        agents[str(event.get("agent", "未標記"))].append(event)

    lines = [
        "<!-- markdownlint-configure-file",
        "{",
        '  "MD013": {',
        '    "line_length": 120,',
        '    "tables": false',
        "  },",
        '  "MD060": {',
        '    "style": "compact"',
        "  }",
        "}",
        "-->",
        "",
        "# 智能體協作修復會後總結",
        "",
        f"- 產生時間：{now}",
        f"- 工作區：`{workspace}`",
        f"- 審計事件數：{len(events)}",
        f"- 總分數變化：{total_score:+d}",
        "",
        "## 任務目標",
        "",
        "讓 Perob 入口、OpenClaw 接管、DesktopBridge 回退與智能體學習標記形成可追蹤閉環。",
        "",
        "## 實際路由",
        "",
        "- 優先路由：Perob API -> OpenClaw Gateway",
        "- 補救路由：OpenClaw 失敗 -> DesktopBridge",
        "- 外圍協調：n8n 維持 optional，不阻斷核心對話",
        "",
        "## 錯誤選擇與補救結果",
        "",
    ]
    if not events:
        lines.extend(
            [
                "- 尚未有審計事件。這代表目前沒有可評分的智能體錯誤選擇或補救紀錄。",
                "- 下一步：執行一次 `/api/openclaw/task` 或工程類 `/api/send_message` 任務後再生成報告。",
            ]
        )
    else:
        lines.append("| 時間 | 智能體 | 規則 | 分工 | 路由 | 選擇 | 結果 | 補救 | 分數 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | ---: |")
        for event in events[-50:]:
            lines.append(
                "| {created_at} | {agent} | {rules} | {assigned} | {route} | {decision} | {outcome} | {remedy} | {score_delta:+d} |".format(
                    created_at=str(event.get("created_at", ""))[:19],
                    agent=str(event.get("agent", "")) or "未標記",
                    rules=_join(event.get("rule_ids")),
                    assigned=_join(event.get("assigned_agents")),
                    route=str(event.get("route", "")) or "未標記",
                    decision=str(event.get("decision", "")).replace("|", "/"),
                    outcome=str(event.get("outcome", "")),
                    remedy=str(event.get("remedy", "")).replace("|", "/"),
                    score_delta=int(event.get("score_delta", 0) or 0),
                )
            )
    learning_events = [
        event
        for event in events
        if event.get("learning_action") or event.get("training_tags") or event.get("next_guardrail")
    ]
    if learning_events:
        lines.extend(["", "## 資料層訓練 Overlay", ""])
        lines.append("| 智能體 | 學習動作 | 訓練標籤 | 下一道護欄 |")
        lines.append("| --- | --- | --- | --- |")
        for event in learning_events[-20:]:
            lines.append(
                "| {agent} | {learning} | {tags} | {guardrail} |".format(
                    agent=str(event.get("agent", "")) or "未標記",
                    learning=str(event.get("learning_action", "")).replace("|", "/") or "—",
                    tags=_join(event.get("training_tags")),
                    guardrail=str(event.get("next_guardrail", "")).replace("|", "/") or "—",
                )
            )
    lines.extend(
        [
            "",
            "## 智能體個別心得",
            "",
        ]
    )
    if not agents:
        lines.append("- 尚無個別心得，等待下一次任務審計資料。")
    else:
        for agent, rows in sorted(agents.items()):
            score = sum(int(e.get("score_delta", 0) or 0) for e in rows)
            success = sum(1 for e in rows if str(e.get("outcome")) == "success")
            failed = len(rows) - success
            lines.extend(
                [
                    f"### {agent}",
                    "",
                    f"- 事件數：{len(rows)}",
                    f"- 成功：{success}，需補救：{failed}",
                    f"- 分數：{score:+d}",
                    "- 心得：下次先確認路由可用性，再決定接管或回退；失敗不可卡住，必須留下補救紀錄。",
                    "",
                ]
            )
    lines.extend(
        [
            "## 下次避免重犯規則",
            "",
        ]
    )
    for idx, (rule_id, rule) in enumerate(TRAINING_RULES.items(), start=1):
        lines.append(
            f"{idx}. `{rule_id}`（負責：{rule['owner']}）：{rule['description']}"
        )
    lines.extend(
        [
            "",
            "## 智能體任務分配",
            "",
            "- 工程師：負責入口檢查順序、proxy、後端、OpenClaw fallback、Python runtime 風險。",
            "- 帽子：負責 OpenClaw token、控制平面、Lobster approval checkpoint 與沙盒安全推演。",
            "- 申言者：負責第一層危險等級分類，不能卡住任務，需轉交帽子或工程師。",
            "- 總管中樞：負責任務分流、審計寫入、扣分加分、報告生成。",
            "- 研究員：負責把錯誤案例轉成 AEG/RAG 弱關聯記憶，避免低信心鬼打牆。",
            "",
            "## 結果摘要",
            "",
            f"- outcome 統計：{dict(outcomes)}",
            f"- 審計來源：`{AUDIT_RELATIVE_PATH}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate agent collaboration review markdown.")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    parser.add_argument("--latest", action="store_true", help="Only include latest audited day.")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    events = _load_events(workspace / AUDIT_RELATIVE_PATH)
    if args.latest:
        events = _filter_latest_day(events)

    out = (
        Path(args.out).expanduser().resolve()
        if args.out
        else workspace / "reports" / f"AGENT_COLLABORATION_REPAIR_REVIEW_{datetime.now():%Y%m%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_markdown(events, workspace), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

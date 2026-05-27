#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a unified collaboration + learning report for all agents."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.agent_prompts import AGENT_SYSTEM_PROMPTS
from core.knowledge_hub import KnowledgeHub
from core.memory_layers import collect_memory_sources
from core.workflow_runtime import run_task_plan


ROLES = ["總管", "研究員", "工程師", "小編", "申言者", "帽子", "通用"]


def _load_conversations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _role_stats(conversations: dict[str, Any]) -> dict[str, dict[str, int]]:
    result = {r: {"threads": 0, "messages": 0} for r in ROLES}
    for _, payload in conversations.items():
        if not isinstance(payload, dict):
            continue
        role = str(payload.get("agent_name", "通用") or "通用")
        role = role if role in result else "通用"
        result[role]["threads"] += 1
        messages = payload.get("messages", [])
        result[role]["messages"] += len(messages) if isinstance(messages, list) else 0
    return result


def _workflow_probe(workspace: Path) -> dict[str, dict[str, Any]]:
    probe_inputs = {
        "總管": "請巡查前後端狀態並整合回報",
        "研究員": "請研究並比較目前系統可用的除錯策略",
        "工程師": "請修復路由與連線問題並提供驗證方法",
        "小編": "請把技術回報整理為可讀摘要",
        "申言者": "請做風險分級並給出放行條件",
        "帽子": "請做安全沙盒推演並提出阻擋策略",
        "通用": "請彙整系統任務現況",
    }
    out: dict[str, dict[str, Any]] = {}
    for role, prompt in probe_inputs.items():
        try:
            result = run_task_plan(workspace, role, prompt)
            task = result.get("task_state", {}) if isinstance(result, dict) else {}
            out[role] = {
                "overall_status": str(task.get("overall_status", "unknown")),
                "completed_steps": int(task.get("completed_steps", 0) or 0),
                "failed_steps": int(task.get("failed_steps", 0) or 0),
            }
        except Exception as exc:
            out[role] = {
                "overall_status": "failed",
                "completed_steps": 0,
                "failed_steps": 1,
                "error": str(exc),
            }
    return out


def build_report(workspace: Path) -> Path:
    now = datetime.now()
    report_dir = workspace / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / f"AGENT_COMMON_STATUS_{now.strftime('%Y%m%d_%H%M%S')}.md"

    hub = KnowledgeHub(workspace)
    rebuild_result = hub.rebuild()
    hub_status = hub.status()
    sources = collect_memory_sources(workspace)
    effective_rebuild = bool(rebuild_result.get("rebuilt")) or int(hub_status.get("total_items", 0) or 0) > 0

    conversations = _load_conversations(workspace / "data" / "agent_memories" / "conversations.json")
    role_usage = _role_stats(conversations)
    workflow_probe = _workflow_probe(workspace)

    missing_blocks = []
    if not hub_status.get("faiss_ready"):
        missing_blocks.append("FAISS 未就緒（目前可能以 sqlite 降級運作）")
    if int(hub_status.get("total_items", 0) or 0) == 0:
        missing_blocks.append("知識中樞索引總量為 0")

    lines: list[str] = []
    lines.append(f"# 智能體共同狀態與學習報告（{now.strftime('%Y-%m-%d %H:%M:%S')}）")
    lines.append("")
    lines.append("## 一、未融合資料補齊結果")
    lines.append(f"- 工作區：`{workspace}`")
    lines.append(
        f"- 知識中樞重建：`{rebuild_result.get('ok')}` / rebuilt=`{rebuild_result.get('rebuilt')}` / effective=`{effective_rebuild}`"
    )
    lines.append(f"- 知識中樞總索引：`{hub_status.get('total_items', 0)}`")
    lines.append(f"- 記憶層狀態：FAISS=`{hub_status.get('faiss_ready')}`")
    lines.append(f"- 納入來源數：`{len(sources)}`")
    if missing_blocks:
        lines.append("- 尚待補強：")
        for item in missing_blocks:
            lines.append(f"  - {item}")
    else:
        lines.append("- 尚待補強：無，主要資料層已完成融合。")
    lines.append("")

    lines.append("## 二、多智能體協作巡查（自動探測）")
    lines.append("| 智能體 | 工作流狀態 | 完成步驟 | 失敗步驟 |")
    lines.append("|---|---:|---:|---:|")
    for role in ROLES:
        row = workflow_probe.get(role, {})
        lines.append(
            f"| {role} | {row.get('overall_status', 'unknown')} | {row.get('completed_steps', 0)} | {row.get('failed_steps', 0)} |"
        )
    lines.append("")

    lines.append("## 三、各智能體個別狀態與心得（共同版）")
    for role in ROLES:
        usage = role_usage.get(role, {"threads": 0, "messages": 0})
        probe = workflow_probe.get(role, {})
        prompt_head = AGENT_SYSTEM_PROMPTS.get(role, AGENT_SYSTEM_PROMPTS.get("總管", "")).splitlines()[0]
        lines.append(f"### {role}")
        lines.append(f"- 狀態：`{probe.get('overall_status', 'unknown')}`")
        lines.append(f"- 任務執行：完成 `{probe.get('completed_steps', 0)}` 步 / 失敗 `{probe.get('failed_steps', 0)}` 步")
        lines.append(f"- 使用量：threads=`{usage['threads']}` / messages=`{usage['messages']}`")
        lines.append(f"- 角色定位：{prompt_head}")
        if probe.get("overall_status") in {"failed", "unknown"}:
            lines.append("- 心得：需要補足工具鏈或上下文，避免角色空轉。")
        elif int(probe.get("failed_steps", 0) or 0) > 0:
            lines.append("- 心得：已可運作，但需降低失敗步驟與重試成本。")
        else:
            lines.append("- 心得：流程穩定，可持續提升回覆精準度與跨角色交接品質。")
        lines.append("")

    lines.append("## 四、外部代理程式優化入口（下一輪）")
    lines.append("- 建議入口：先由申言者做風險分級，再交帽子沙盒推演，最後工程師落地修復。")
    lines.append("- 若啟用外部代理：必須保留審計紀錄（誰觸發、執行什麼、是否過沙盒）。")
    lines.append("- 最低權限 ON 時，仍建議保留『危險動作二次確認』與『回滾方案』。")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    workspace = BASE_DIR
    out_path = build_report(workspace)
    print(str(out_path))


if __name__ == "__main__":
    main()

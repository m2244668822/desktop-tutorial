#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph 工作流骨架：
Planner -> Router -> Executor -> Verifier -> MemoryWriter
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict


BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False
    END = "END"
    START = "START"
    StateGraph = None

try:
    from agent_memory_manager import AgentMemoryManager
except Exception:
    AgentMemoryManager = None

try:
    from local_memory_api import LocalMemoryAPI
except Exception:
    LocalMemoryAPI = None

try:
    from core.workflow_runtime import run_task_plan
except Exception:
    run_task_plan = None


class WorkflowState(TypedDict, total=False):
    user_input: str
    workspace: str
    plan: str
    route: str
    result: str
    tool_outputs: dict[str, Any]
    task_state: dict[str, Any]
    verified: bool
    verification_notes: str
    memory_record: dict[str, Any]
    prompt_context: str
    trace: list[str]
    collaboration: dict[str, Any]
    risk_level: str
    precheck_owner: str


def _append_trace(state: WorkflowState, message: str) -> WorkflowState:
    trace = list(state.get("trace", []))
    trace.append(message)
    state["trace"] = trace
    return state


def _new_handoff(
    owner: str,
    next_owner: str,
    goal: str,
    inputs: list[str],
    outputs: list[str],
    risks: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(),
        "owner": owner,
        "next_owner": next_owner,
        "goal": goal,
        "inputs": inputs,
        "outputs": outputs,
        "risks": risks,
        "next_action": next_action,
    }


def _append_handoff(state: WorkflowState, handoff: dict[str, Any]) -> None:
    collaboration = dict(state.get("collaboration", {}))
    handoffs = list(collaboration.get("handoffs", []))
    handoffs.append(handoff)
    collaboration["handoffs"] = handoffs
    state["collaboration"] = collaboration


def planner_node(state: WorkflowState) -> WorkflowState:
    text = state.get("user_input", "").strip()
    if any(token in text for token in ["修", "錯誤", "bug", "debug", "fix"]):
        plan = "先診斷問題，再修改程式，最後驗證。"
    elif any(
        token in text
        for token in ["倫理", "道德", "聖經", "以利亞", "先知", "申言者", "價值"]
    ):
        plan = "先檢索相關文本，再做倫理脈絡分析，最後給出可執行建議。"
    elif any(token in text for token in ["研究", "比較", "查詢", "資料"]):
        plan = "先檢索資料，再整理比較，最後輸出建議。"
    else:
        plan = "先理解需求，再分派角色，最後回寫記憶。"
    state["plan"] = plan
    _append_handoff(
        state,
        _new_handoff(
            owner="Planner",
            next_owner="Router",
            goal="將需求轉成可執行計畫並準備路由",
            inputs=[
                _format_prompt_memory_context(
                    state.get("tool_outputs", {}), max_items=1, max_chars=120
                )
                or "user_input"
            ],
            outputs=[plan],
            risks=["需求語意不完整可能造成錯路由"],
            next_action="根據需求關鍵詞選擇主責角色",
        ),
    )
    return _append_trace(state, f"planner:{plan}")


def router_node(state: WorkflowState) -> WorkflowState:
    text = state.get("user_input", "").lower()
    collaboration_needed = False
    risk_level = "L0"
    precheck_owner = "無"
    security_tokens = ["安全", "漏洞", "掃描", "入侵", "權限", "金鑰", "憑證", "攻擊", "防火牆", "cors"]
    engineering_tokens = ["程式", "修復", "修正", "bug", "工程", "前端", "後端", "api", "route", "debug"]
    policy_tokens = ["危險", "風險", "越權", "倫理", "道德", "邊界", "申言者", "許可"]

    if any(token in text for token in security_tokens):
        route = "帽子"
        risk_level = "L2"
        precheck_owner = "申言者"
    elif any(token in text for token in policy_tokens):
        route = "申言者"
        risk_level = "L2"
        precheck_owner = "申言者"
    elif any(token in text for token in ["提案", "協作流程", "治理"]):
        route = "申言者"
    elif any(token in text for token in ["研究", "比較", "開源", "調查"]):
        route = "研究員"
    elif any(token in text for token in engineering_tokens):
        route = "工程師"
        risk_level = "L1"
        precheck_owner = "申言者"
    else:
        route = "申言者"
        
    # 溝通巡查：偵測是否需要跨領域協作
    if len(text) > 100 or any(t in text for t in ["整合", "架構", "全面"]):
        collaboration_needed = True
        
    state["route"] = route
    state["risk_level"] = risk_level
    state["precheck_owner"] = precheck_owner

    handoff_goal = f"為本次任務指定主責角色：{route}"
    if collaboration_needed:
        handoff_goal += "（建議啟動跨角色溝通巡查模式）"
    if precheck_owner != "無":
        handoff_goal += f"；先經{precheck_owner}風險分級({risk_level})"
        
    _append_handoff(
        state,
        _new_handoff(
            owner="Router",
            next_owner="Executor",
            goal=handoff_goal,
            inputs=[state.get("plan", ""), state.get("user_input", "")[:120]],
            outputs=[f"route={route}", f"collaboration={collaboration_needed}"],
            risks=["路由誤判會影響工具選擇與成本"],
            next_action="執行工具鏈並收集巡查快照",
        ),
    )
    return _append_trace(state, f"router:{route}{'+collab' if collaboration_needed else ''}")


def _format_prompt_memory_context(
    tool_outputs: dict[str, Any], max_items: int = 3, max_chars: int = 600
) -> str:
    layered = tool_outputs.get("context_layers", {})
    layer_values = layered.get("layers", {}) if isinstance(layered, dict) else {}
    if layer_values:
        lines = ["[分層上下文 L0/L1/L2]"]
        used_chars = len(lines[0])
        for layer_name in ("l0", "l1", "l2"):
            entries = layer_values.get(layer_name, [])
            for idx, item in enumerate(entries[:max_items], start=1):
                summary = " ".join(str(item.get("summary", "")).split())
                if not summary:
                    continue
                line = f"{layer_name.upper()}-{idx}: {summary[:150]}"
                if used_chars + len(line) > max_chars:
                    return "\n".join(lines)
                lines.append(line)
                used_chars += len(line)
        if len(lines) > 1:
            return "\n".join(lines)

    memories = tool_outputs.get("long_term_memory", {})
    matches = memories.get("matches", [])
    if not matches:
        return ""

    lines = ["[工作流長期記憶]"]
    used_chars = len(lines[0])
    for idx, item in enumerate(matches[:max_items], start=1):
        source = item.get("source", "unknown")
        timestamp = str(item.get("timestamp", "") or "未知時間")[:19]
        summary = " ".join(str(item.get("summary", "")).split())
        if not summary:
            continue
        line = f"{idx}. 來源={source} | 時間={timestamp} | 摘要={summary[:160]}"
        if used_chars + len(line) > max_chars:
            break
        lines.append(line)
        used_chars += len(line)
    return "\n".join(lines) if len(lines) > 1 else ""


def _format_research_result(tool_outputs: dict[str, Any]) -> str:
    catalog = tool_outputs.get("catalog", {})
    aeg = tool_outputs.get("aeg_keyword_graph", {})
    lines = ["研究工具結果："]
    for item in catalog.get("matches", []):
        lines.append(
            f"- {item.get('name')} | {item.get('focus')} | {item.get('release')}"
        )
        lines.append(f"  {item.get('url')}")
    hub = tool_outputs.get("knowledge_hub", {})
    lines.append(f"知識中樞：{'就緒' if hub.get('exists') else '未就緒'}")
    lines.append(
        f"ChatGPT 資料庫：{'可用' if hub.get('chatgpt_database_ready') else '未就緒'}"
    )
    memories = tool_outputs.get("long_term_memory", {})
    for item in memories.get("matches", [])[:3]:
        lines.append(f"記憶片段[{item.get('source')}]：{item.get('summary')}")
    if aeg:
        lines.append(
            f"AEG 關聯圖：sources={aeg.get('sources_seen', 0)} · texts={aeg.get('text_items', 0)} · keywords={aeg.get('keywords_count', 0)}"
        )
        top = aeg.get("top_keywords", [])[:8]
        if top:
            lines.append("AEG 熱點關鍵字：" + "、".join(str(x.get("keyword", "")) for x in top if x.get("keyword")))
    if tool_outputs.get("write_knowledge_note", {}).get("path"):
        lines.append(f"知識筆記：{tool_outputs['write_knowledge_note']['path']}")
    if tool_outputs.get("save_workspace_report", {}).get("path"):
        lines.append(f"工作流報告：{tool_outputs['save_workspace_report']['path']}")
    return "\n".join(lines)


def _format_engineering_result(tool_outputs: dict[str, Any]) -> str:
    api = tool_outputs.get("api_config", {})
    ws = tool_outputs.get("workspace_status", {})
    hub = tool_outputs.get("knowledge_hub", {})
    providers = api.get("providers", [])
    enabled_count = len([p for p in providers if p.get("enabled")])
    lines = [
        "工程工具結果：",
        f"- API 金鑰來源: {api.get('key_source', '未知')}",
        f"- API 金鑰狀態: {api.get('key_state', '未知')}",
        f"- OPENAI_BASE_URL: {api.get('base_url', '未知')}",
        f"- OPENAI_MODEL: {api.get('model', '未知')}",
        f"- OPEN_SOURCE_CHAT_MODEL: {api.get('open_source_model', '未知')}",
        f"- 已啟用供應商: {enabled_count}/{len(providers)}",
        f"- 知識中樞: {'就緒' if hub.get('exists') else '未就緒'}",
        f"- 長期記憶層: {'可用' if tool_outputs.get('long_term_memory', {}).get('status', {}).get('faiss_ready') else '未就緒'}",
        f"- Git 摘要:\n{ws.get('git_summary', '無')}",
    ]
    for item in providers[:5]:
        lines.append(
            f"- 供應商 {item.get('name')}: {item.get('key_state')} ({item.get('tier')})"
        )
    if tool_outputs.get("write_knowledge_note", {}).get("path"):
        lines.append(f"- 知識筆記: {tool_outputs['write_knowledge_note']['path']}")
    if tool_outputs.get("save_workspace_report", {}).get("path"):
        lines.append(f"- 工作流報告: {tool_outputs['save_workspace_report']['path']}")
    return "\n".join(lines)


def _format_manager_result(tool_outputs: dict[str, Any]) -> str:
    api = tool_outputs.get("api_config", {})
    hub = tool_outputs.get("knowledge_hub", {})
    ws = tool_outputs.get("workspace_status", {})
    providers = api.get("providers", [])
    enabled_count = len([p for p in providers if p.get("enabled")])
    long_term_status = tool_outputs.get("long_term_memory", {}).get("status", {})
    chatgpt_ready = bool(hub.get("chatgpt_database_ready"))
    sqlite_faiss_ready = bool(
        hub.get("faiss_ready") or long_term_status.get("faiss_ready")
    )
    lines = [
        "申言者中樞工具結果（原總管相容輸出）：",
        f"- 工作區: {ws.get('workspace', '')}",
        f"- VS Code 工作區: {'是' if ws.get('vscode_workspace_exists') else '否'}",
        f"- NVIDIA/OPENAI 模型: {api.get('model', '未設定')}",
        f"- 本地模型: {api.get('open_source_model', '未設定')}",
        f"- API 供應商啟用數: {enabled_count}/{len(providers)}",
        f"- ChatGPT 長期記憶庫: {'就緒' if chatgpt_ready else '未就緒'}",
        f"- SQLite + FAISS: {'就緒' if sqlite_faiss_ready else '未就緒'}",
        f"- 記憶索引筆數: {hub.get('total_items') or long_term_status.get('total_items') or 0}",
        f"- 知識中樞 manifest: {hub.get('manifest_path', '')}",
    ]
    for item in providers[:5]:
        lines.append(
            f"- 供應商 {item.get('name')}: {item.get('key_state')} ({item.get('tier')})"
        )
    if tool_outputs.get("read_file", {}).get("path"):
        lines.append(f"- 已讀取檔案: {tool_outputs['read_file']['path']}")
    if tool_outputs.get("build_knowledge_ingestion", {}).get("built"):
        ingestion = tool_outputs["build_knowledge_ingestion"]
        lines.append(f"- 導入文件數: {ingestion.get('document_count', 0)}")
        lines.append(f"- 導入 chunks: {ingestion.get('chunk_count', 0)}")
        lines.append(f"- documents.jsonl: {ingestion.get('documents_path', '')}")
        lines.append(f"- chunks.jsonl: {ingestion.get('chunks_path', '')}")
    if tool_outputs.get("write_knowledge_note", {}).get("path"):
        lines.append(f"- 知識筆記: {tool_outputs['write_knowledge_note']['path']}")
    if tool_outputs.get("save_workspace_report", {}).get("path"):
        lines.append(f"- 工作流報告: {tool_outputs['save_workspace_report']['path']}")
    return "\n".join(lines)


def _format_security_result(tool_outputs: dict[str, Any]) -> str:
    ws = tool_outputs.get("workspace_status", {})
    return "\n".join(
        [
            "安全工具結果：",
            "- 目前先使用工作區/版本狀態作為安全前檢。",
            f"- Git 摘要:\n{ws.get('git_summary', '無')}",
            "- 下一步可接帽子智能體與真正的掃描工具。",
        ]
    )


def _score_memory_match(item: dict[str, Any]) -> float:
    scores = []
    for key in ("exact_match", "semantic_score", "lexical_score", "combined_score", "score"):
        try:
            scores.append(float(item.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    return max(scores) if scores else 0.0


def _memory_summary_line(item: dict[str, Any], idx: int) -> str:
    source = str(item.get("source", "unknown") or "unknown")
    timestamp = str(item.get("timestamp", "") or "")[:19]
    summary = " ".join(str(item.get("summary") or item.get("content") or "").split())
    score = _score_memory_match(item)
    time_part = f" · {timestamp}" if timestamp else ""
    score_part = f" · 關聯分數 {score:.2f}" if score else " · 弱關聯"
    return f"  - [{idx}] {source}{time_part}{score_part}：{summary[:140]}"


def _format_contextual_miss_guidance(user_input: str, memories: list[dict[str, Any]]) -> list[str]:
    text = str(user_input or "").strip()
    lines = [
        "- 目前沒有高信心直接命中；已改用「前後文 + 長期記憶 + 弱關聯」分析，不再硬導向無關索引。",
    ]
    if memories:
        lines.append("- 可用的弱關聯記憶片段（前 3 筆）：")
        for idx, item in enumerate(memories[:3], start=1):
            if isinstance(item, dict):
                lines.append(_memory_summary_line(item, idx))
    else:
        lines.append("- 長期記憶也沒有可用片段；這代表需要先建立本題的種子筆記。")

    focus_terms = [
        token
        for token in ("鬼打牆", "需求分流", "前後文", "關鍵字", "RAG", "AEG", "智能體", "對話品質", "路由", "fallback")
        if token.lower() in text.lower()
    ]
    if not focus_terms:
        focus_terms = ["需求分流", "前後文", "對話品質", "RAG 檢索"]
    lines.extend(
        [
            "- 更好的處理方式：先把你的需求拆成「症狀、想要結果、限制、是否要動手」四格，再決定交給哪個智能體。",
            "- 建議補查關鍵詞：" + "、".join(focus_terms[:6]),
            "- 如果下一輪仍低信心，應回問一個具體缺口，而不是重複模板或假裝已命中。",
        ]
    )
    return lines


def _format_prophet_result(tool_outputs: dict[str, Any], user_input: str = "") -> str:
    hub = tool_outputs.get("knowledge_hub", {})
    memories = tool_outputs.get("long_term_memory", {})
    workspace_hits = tool_outputs.get("workspace_search", {}).get("matches", [])
    catalog = tool_outputs.get("catalog", {})
    memory_matches = [
        item for item in memories.get("matches", []) if isinstance(item, dict)
    ]
    direct_memory_hits = [
        item for item in memory_matches if _score_memory_match(item) >= 0.35
    ]
    lines = [
        "申言者工具結果：",
        f"- 知識中樞：{'就緒' if hub.get('exists') else '未就緒'}",
        f"- 長期記憶命中：{len(memory_matches)} 筆",
    ]
    if workspace_hits:
        lines.append("- 工作區關鍵命中（前 5 筆）：")
        lines.extend([f"  - {item}" for item in workspace_hits[:5]])
    if catalog.get("matches"):
        lines.append("- 相關程式資源（前 3 筆）：")
        for item in catalog.get("matches", [])[:3]:
            lines.append(f"  - {item.get('name')} | {item.get('focus')}")
            lines.append(f"    {item.get('url')}")
    if direct_memory_hits and not workspace_hits and not catalog.get("matches"):
        lines.append("- 長期記憶高信心命中（前 3 筆）：")
        for idx, item in enumerate(direct_memory_hits[:3], start=1):
            lines.append(_memory_summary_line(item, idx))
    if not workspace_hits and not catalog.get("matches") and not direct_memory_hits:
        lines.extend(_format_contextual_miss_guidance(user_input, memory_matches))
    return "\n".join(lines)


def executor_node(state: WorkflowState) -> WorkflowState:
    workspace = Path(state.get("workspace", str(BASE_DIR))).expanduser().resolve()
    route = state.get("route", "申言者")
    risk_level = state.get("risk_level", "L0")
    precheck_owner = state.get("precheck_owner", "無")
    user_input = state.get("user_input", "")
    if run_task_plan:
        task_run = run_task_plan(workspace, route, user_input)
        task_state = task_run.get("task_state", {})
        raw_outputs = task_run.get("tool_outputs", {})
        tool_outputs = {
            "context_layers": raw_outputs.get("context_layers", {}),
            "knowledge_hub": raw_outputs.get("knowledge_hub_manifest", {}),
            "workspace_status": raw_outputs.get("workspace_status", {}),
            "long_term_memory": raw_outputs.get("long_term_memory", {}),
        }
        if "open_source_catalog" in raw_outputs:
            tool_outputs["catalog"] = raw_outputs["open_source_catalog"]
        if "api_config" in raw_outputs:
            tool_outputs["api_config"] = raw_outputs["api_config"]
        if "workspace_search" in raw_outputs:
            tool_outputs["workspace_search"] = raw_outputs["workspace_search"]
        if "aeg_keyword_graph" in raw_outputs:
            tool_outputs["aeg_keyword_graph"] = raw_outputs["aeg_keyword_graph"]
        if "read_file" in raw_outputs:
            tool_outputs["read_file"] = raw_outputs["read_file"]
    else:
        task_state = {
            "overall_status": "failed",
            "steps": [],
            "log_path": "",
            "tool_registry": {},
        }
        tool_outputs = {
            "context_layers": {},
            "knowledge_hub": {},
            "workspace_status": {},
            "long_term_memory": {},
        }

    if route == "研究員":
        result = _format_research_result(tool_outputs)
    elif route == "申言者":
        result = _format_prophet_result(tool_outputs, user_input=user_input)
    elif route == "工程師":
        result = _format_engineering_result(tool_outputs)
    elif route == "帽子":
        result = _format_security_result(tool_outputs)
    else:
        result = _format_manager_result(tool_outputs)

    state["tool_outputs"] = tool_outputs
    state["task_state"] = task_state
    state["result"] = result
    state["prompt_context"] = _format_prompt_memory_context(tool_outputs)
    risks: list[str] = []
    if int(task_state.get("failed_steps", 0) or 0) > 0:
        risks.append("部分工具步驟失敗，結果可能不完整")
    if not state.get("prompt_context"):
        risks.append("未注入足夠上下文")
    _append_handoff(
        state,
        _new_handoff(
            owner="Executor",
            next_owner="Reviewer",
            goal="執行工具鏈並產出可檢查結果",
            inputs=[f"route={route}", f"risk_level={risk_level}", f"precheck={precheck_owner}", state.get("plan", "")],
            outputs=[
                f"overall_status={task_state.get('overall_status', '')}",
                f"completed_steps={task_state.get('completed_steps', 0)}",
            ],
            risks=risks or ["無顯著風險"],
            next_action="核驗結果完整性與任務通過條件",
        ),
    )
    return _append_trace(state, f"executor:{route}:tools")


def verifier_node(state: WorkflowState) -> WorkflowState:
    result = state.get("result", "")
    task_state = state.get("task_state", {})
    overall_status = task_state.get("overall_status", "failed")
    completed_steps = int(task_state.get("completed_steps", 0) or 0)
    failed_steps = int(task_state.get("failed_steps", 0) or 0)
    verified = (
        bool(result.strip())
        and overall_status in {"success", "partial"}
        and completed_steps > 0
    )
    if verified:
        notes = f"任務狀態 {overall_status}；完成 {completed_steps} 步，失敗 {failed_steps} 步。"
    else:
        notes = f"任務驗證未通過；狀態={overall_status}，完成={completed_steps}，失敗={failed_steps}。"
    state["verified"] = verified
    state["verification_notes"] = notes
    _append_handoff(
        state,
        _new_handoff(
            owner="Reviewer",
            next_owner="MemoryWriter",
            goal="審核執行結果與是否可寫入記憶",
            inputs=[
                state.get("result", "")[:120],
                str(state.get("task_state", {}).get("overall_status", "")),
            ],
            outputs=[f"verified={verified}", notes],
            risks=[] if verified else ["驗證未通過，禁止升級長期記憶"],
            next_action="記錄結果並寫入可觀測事件",
        ),
    )
    return _append_trace(state, f"verifier:{notes}")


def memory_writer_node(state: WorkflowState) -> WorkflowState:
    record = {
        "timestamp": datetime.now().isoformat(),
        "route": state.get("route", "申言者"),
        "plan": state.get("plan", ""),
        "verified": state.get("verified", False),
        "tool_keys": sorted(list((state.get("tool_outputs") or {}).keys())),
        "prompt_context_ready": bool(state.get("prompt_context")),
        "task_id": (state.get("task_state") or {}).get("task_id", ""),
        "task_status": (state.get("task_state") or {}).get("overall_status", ""),
        "task_log_path": (state.get("task_state") or {}).get("log_path", ""),
        "trace_id": (state.get("task_state") or {}).get("trace_id", ""),
        "handoff_count": len((state.get("collaboration") or {}).get("handoffs", [])),
    }
    state["memory_record"] = record

    if AgentMemoryManager:
        try:
            manager = AgentMemoryManager(
                state.get("workspace", str(BASE_DIR)), auto_save=False
            )
            manager.save_agent_memory("LangGraphWorkflow", record)
        except Exception:
            pass

    return _append_trace(state, "memory_writer:done")


def build_workflow():
    if not LANGGRAPH_AVAILABLE or StateGraph is None:
        raise RuntimeError("LangGraph 未安裝，請先安裝 langgraph。")

    graph = StateGraph(WorkflowState)
    graph.add_node("Planner", planner_node)
    graph.add_node("Router", router_node)
    graph.add_node("Executor", executor_node)
    graph.add_node("Verifier", verifier_node)
    graph.add_node("MemoryWriter", memory_writer_node)

    graph.add_edge(START, "Planner")
    graph.add_edge("Planner", "Router")
    graph.add_edge("Router", "Executor")
    graph.add_edge("Executor", "Verifier")
    graph.add_edge("Verifier", "MemoryWriter")
    graph.add_edge("MemoryWriter", END)
    return graph.compile()


def run_workflow(user_input: str, workspace: str | None = None) -> WorkflowState:
    app = build_workflow()
    state: WorkflowState = {
        "user_input": user_input,
        "workspace": workspace or str(BASE_DIR),
        "trace": [],
    }
    return app.invoke(state)

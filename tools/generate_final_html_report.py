#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.knowledge_hub import KnowledgeHub
from core.workflow_runtime import run_task_plan


def _safe_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _count_conversations(path: Path) -> int:
    data = _safe_json(path, {})
    if isinstance(data, dict):
        return len(data)
    if isinstance(data, list):
        return len(data)
    return 0


def _count_messages(path: Path) -> int:
    data = _safe_json(path, {})
    if not isinstance(data, dict):
        return 0
    total = 0
    for _, conv in data.items():
        if isinstance(conv, dict):
            total += len(conv.get("messages", []) or [])
    return total


def build_report(workspace: Path) -> Path:
    now = datetime.now()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = reports / f"FINAL_SYSTEM_REPORT_{now.strftime('%Y%m%d_%H%M%S')}.html"

    current_conv = workspace / "data" / "agent_memories" / "conversations.json"
    hdd_conv = workspace / "data_hdd_storage" / "agent_memories" / "conversations.json"
    legacy_conv = workspace / "500" / "llama32-chat" / "data" / "conversations.json"

    current_threads = _count_conversations(current_conv)
    current_msgs = _count_messages(current_conv)
    hdd_threads = _count_conversations(hdd_conv)
    legacy_rows = _count_conversations(legacy_conv)

    hub = KnowledgeHub(workspace)
    hub_status = hub.status()
    rebuild = hub.rebuild()
    hub_after = hub.status()

    # 研究員流程抽樣（觸發 AEG/搜尋鏈）
    research_probe = run_task_plan(workspace, "research", "請提取本地 GPT 關鍵字關聯並回報")
    task_state = research_probe.get("task_state", {}) if isinstance(research_probe, dict) else {}
    tool_outputs = research_probe.get("tool_outputs", {}) if isinstance(research_probe, dict) else {}
    aeg = tool_outputs.get("aeg_keyword_graph", {}) if isinstance(tool_outputs, dict) else {}

    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>系統最終整合報告</title>
  <style>
    :root {{
      --bg: #071224;
      --panel: #0d1b33;
      --ink: #e9f0ff;
      --muted: #99a9c7;
      --ok: #3ddc97;
      --warn: #ffb020;
      --bad: #ff5d73;
      --line: #1f355f;
      --accent: #52a0ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Noto Sans TC", "PingFang TC", sans-serif;
      background: radial-gradient(1200px 800px at 80% -10%, #1d3a6d 0%, var(--bg) 50%);
      color: var(--ink);
      line-height: 1.65;
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 64px; }}
    .hero {{
      background: linear-gradient(145deg, #0f2446, #0a1730);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 22px 20px;
      box-shadow: 0 12px 36px rgba(0,0,0,.35);
    }}
    h1 {{ margin: 0; font-size: 30px; letter-spacing: .5px; }}
    .sub {{ color: var(--muted); margin-top: 6px; font-size: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-top: 16px; }}
    .kpi {{
      background: #0b1830; border: 1px solid var(--line); border-radius: 12px; padding: 12px;
    }}
    .kpi .k {{ color: var(--muted); font-size: 12px; }}
    .kpi .v {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .panel {{
      margin-top: 18px; background: var(--panel); border: 1px solid var(--line);
      border-radius: 14px; padding: 16px;
    }}
    h2 {{ margin: 0 0 10px; font-size: 20px; }}
    h3 {{ margin: 14px 0 8px; font-size: 16px; color: #cfe0ff; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: left; }}
    th {{ color: #c6d6f5; font-weight: 700; }}
    .tag {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; border:1px solid var(--line); }}
    .ok {{ color: var(--ok); border-color: rgba(61,220,151,.4); background: rgba(61,220,151,.08); }}
    .warn {{ color: var(--warn); border-color: rgba(255,176,32,.4); background: rgba(255,176,32,.08); }}
    .bad {{ color: var(--bad); border-color: rgba(255,93,115,.4); background: rgba(255,93,115,.08); }}
    .muted {{ color: var(--muted); }}
    code {{ background:#0a1730; padding:2px 6px; border-radius:6px; }}
    ul {{ margin: 8px 0 0 18px; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: repeat(2,1fr); }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>AI 智能體中心：最終整合報告</h1>
      <div class="sub">生成時間：{now.strftime("%Y-%m-%d %H:%M:%S")}（Asia/Taipei）</div>
      <div class="grid">
        <div class="kpi"><div class="k">當前對話 Threads</div><div class="v">{current_threads}</div></div>
        <div class="kpi"><div class="k">當前訊息總量</div><div class="v">{current_msgs}</div></div>
        <div class="kpi"><div class="k">知識中樞索引</div><div class="v">{hub_after.get("total_items", 0)}</div></div>
        <div class="kpi"><div class="k">FAISS 狀態</div><div class="v">{'ON' if hub_after.get("faiss_ready") else 'OFF'}</div></div>
      </div>
    </section>

    <section class="panel">
      <h2>一、問題根因（為何前端對話紀錄消失）</h2>
      <p>主因不是資料被刪除，而是<strong>資料來源切換後未完成融合</strong>。前端主要讀取 <code class="mono">data/agent_memories/conversations.json</code>，
      但大量舊資料在 <code class="mono">data_hdd_storage/agent_memories/conversations.json</code> 與
      <code class="mono">500/llama32-chat/data/conversations.json</code>。</p>
      <table>
        <tr><th>來源</th><th>筆數</th><th>說明</th></tr>
        <tr><td>目前主檔</td><td>{current_threads}</td><td>前端預設讀取</td></tr>
        <tr><td>HDD 舊記憶</td><td>{hdd_threads}</td><td>同格式可直接併回</td></tr>
        <tr><td>舊 GPT list</td><td>{legacy_rows}</td><td>需轉換成統一 thread 結構</td></tr>
      </table>
    </section>

    <section class="panel">
      <h2>二、已完成修復與補強</h2>
      <ul>
        <li>已加入「對話自動恢復」：若主檔過少，會從 HDD 舊記憶與舊 GPT list 安全合併（不覆蓋現有）。</li>
        <li>已補上 <code class="mono">/history</code> API 回傳，前端歷史對話不再只顯示空集合。</li>
        <li>已加強知識中樞重建：無 FAISS 時也會完整寫入 SQLite，避免索引數顯示 0。</li>
        <li>已新增研究員 AEG 工具（本地 GPT 關鍵字與關聯圖抽取）。</li>
      </ul>
      <h3>知識中樞重建結果</h3>
      <pre class="mono muted">{json.dumps(rebuild, ensure_ascii=False, indent=2)}</pre>
    </section>

    <section class="panel">
      <h2>三、向量加速現況</h2>
      <p>目前狀態：{('<span class="tag warn">FAISS 未啟用（sqlite_only）</span>' if not hub_after.get('faiss_ready') else '<span class="tag ok">FAISS 已啟用</span>')}</p>
      <ul>
        <li>可用性：系統可在 sqlite-only 正常運作。</li>
        <li>風險：語意檢索速度與召回品質低於 FAISS 模式。</li>
        <li>建議：依 runbook 啟用 <code class="mono">faiss-cpu</code>，完成後再重建索引。</li>
      </ul>
      <p class="muted">Runbook：<code class="mono">docs/runbooks/knowledge_hub_faiss_enablement.md</code></p>
    </section>

    <section class="panel">
      <h2>四、研究員 AEG 協作（本地 GPT 關聯分析）</h2>
      <p>研究員現在可透過 AEG 工具，自動從本地對話抽取關鍵字與共現關聯，提供其他智能體協作搜尋與推理對照。</p>
      <table>
        <tr><th>欄位</th><th>值</th></tr>
        <tr><td>workflow 狀態</td><td>{task_state.get("overall_status", "unknown")}</td></tr>
        <tr><td>完成步驟</td><td>{task_state.get("completed_steps", 0)}</td></tr>
        <tr><td>失敗步驟</td><td>{task_state.get("failed_steps", 0)}</td></tr>
        <tr><td>AEG sources</td><td>{aeg.get("sources_seen", 0)}</td></tr>
        <tr><td>AEG text_items</td><td>{aeg.get("text_items", 0)}</td></tr>
        <tr><td>AEG keywords</td><td>{aeg.get("keywords_count", 0)}</td></tr>
      </table>
      <p class="muted">輸出位置：<code class="mono">data/knowledge_hub/aeg_keyword_graph.json</code></p>
    </section>

    <section class="panel">
      <h2>五、下一步建議（可直接執行）</h2>
      <ol>
        <li>重啟 web server，前端重新拉取歷史：<code class="mono">python3 desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite</code></li>
        <li>執行 FAISS 啟用流程並重建索引。</li>
        <li>將 AEG 結果定時寫入報告，作為跨智能體共用檢索層。</li>
      </ol>
      <p class="muted">本報告為實際狀態快照，不是靜態模板。</p>
    </section>
  </div>
</body>
</html>
"""
    out.write_text(html, encoding="utf-8")
    return out


def main():
    workspace = BASE_DIR
    out = build_report(workspace)
    print(str(out))


if __name__ == "__main__":
    main()

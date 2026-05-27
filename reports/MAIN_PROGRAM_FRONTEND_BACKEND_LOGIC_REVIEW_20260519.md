# 主程式前後端邏輯審查與改善報告

- 日期：2026-05-19
- 工作區：`/Volumes/智能體/城城城程式`
- 主入口：`system_main.py` -> `desktop_chat_app.py --web-server`
- 主要前端：`templates/chat.html`
- 核心後端：`desktop_chat_app.py`, `core/langgraph_workflow.py`, `core/workflow_runtime.py`, `core/llm_cns.py`
- 驗證：`python3 -m py_compile` 通過
- 可攜性掃描：`reports/portable_workspace_audit_20260519_logic_review.json`

## 1. 總評

目前系統已經具備「桌面智能體中樞」的雛形：有單一入口、Web server 模式、智能體角色、LLM provider 路由、任務狀態機、RAG/長期記憶、前端任務面板、背景自治 daemon 與 Git/跨平台遷移意識。

最大的優點是功能覆蓋很廣，且很多能力已經串起來：使用者輸入會進入前端，前端送到 `/chat/agent`，後端進入 `DesktopBridge.send_message()`，再進入語義分析、工作流規劃、LLM 回覆、記憶寫入與前端狀態同步。

最大的風險是「太多核心職責集中在 `desktop_chat_app.py`」：它同時是 HTTP server、API router、LLM client、agent prompt manager、memory coordinator、task board adapter、file upload server、status monitor。這會讓每次新增功能都更容易互相干擾，也會讓 Windows/Mac 兼容、SMP 多 worker、PostgreSQL 遷移變得比較辛苦。

## 2. 現行邏輯圖

```text
system_main.py
  -> desktop_chat_app.py --web-server
      -> ThreadingHTTPServer
          -> templates/chat.html
          -> /chat/agent
          -> /api/frontend/snapshot
          -> /agent/tasks
          -> /api/providers/status
          -> /api/upload_file

templates/chat.html
  -> state / busy / polling
  -> sendMessage()
      -> POST /chat/agent
      -> render assistant bubble
      -> syncAfterChat()

DesktopBridge.send_message()
  -> analyze_message()
  -> _reply_for_role()
  -> _structured_manager_reply()
      -> core.langgraph_workflow.run_workflow()
          -> Planner -> Router -> Executor -> Verifier -> MemoryWriter
              -> core.workflow_runtime.run_task_plan()
                  -> ToolSpec registry
                  -> context_layers / api_config / workspace_status / RAG / reports
      -> _preferred_backend_reply()
          -> cloud provider first
          -> open_source fallback for discussion
          -> offline fallback
  -> save conversation memory
```

## 3. 後端邏輯層

### 3.1 Entry Point

`system_main.py` 已經是正確方向。它把 `web`, `desktop`, `health`, `autopilot` 做成單一 CLI，這符合你想要的「主程式聚集成一個系統」。

目前問題：

- `system_main.py` 本身很乾淨，但只負責啟動，真正複雜度仍全部落在 `desktop_chat_app.py`。
- 健康檢查是啟動前 gate，但缺少「HTTP server 啟動後端點驗證」。
- SMP 需求還沒真正落地；現在是 `ThreadingHTTPServer`，不是 Gunicorn/Uvicorn worker 模式。

改善方向：

- 保留 `system_main.py` 為唯一人類入口。
- 新增 `app/server.py` 或 `server_main.py`，把 `ThreadingHTTPServer` 替換成 ASGI/FastAPI。
- `system_main.py web` 最終應該啟動 `uvicorn app.server:app --workers N` 或 `gunicorn -k uvicorn.workers.UvicornWorker`。

### 3.2 API Router

目前 API route 全部寫在 `run_web_server_mode()` 的 inner `Handler` class。這可以跑，但維護成本高。

主要問題：

- route 與商業邏輯混在一起。
- 同一個狀態概念有多個 endpoint：`/status`, `/api/get_status`, `/api/frontend/snapshot`, `/api/providers/status`。
- 部分 endpoint 是真資料，部分是 placeholder，例如 `/api/tasks/summary` 固定回傳 completed=1。
- 失敗回應格式不統一，有些是 `{ok:false,error}`, 有些是 `{error}`, 有些是 HTTP 404 text。

改善方向：

- 抽出 `api/routes/chat.py`, `api/routes/status.py`, `api/routes/tasks.py`, `api/routes/files.py`。
- 統一 response envelope：

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "meta": {
    "request_id": "...",
    "duration_ms": 0
  }
}
```

- 所有 endpoint 都要支援 `request_id`，方便前端、log、agent workflow 對齊。

### 3.3 LLM CNS

`core/llm_cns.py` 是剛開始建立的正確方向，應該繼續把 provider 決策搬出 `desktop_chat_app.py`。

目前問題：

- `desktop_chat_app.py` 仍有自己的 `_load_merged_env_data`, `_provider_matrix`, `_api_health`, `_resolve_cloud_provider_config`。
- `core/workflow_runtime.py` 已接 `llm_snapshot()`，但前端 provider 卡片仍由 `desktop_chat_app.py` 的本地邏輯提供。
- LLM fallback 規則散在 `_preferred_backend_reply()`、`allow_open_source_for_purpose()`、`_energy_route_policy()`。

改善方向：

- `core/llm_cns.py` 升級成唯一 LLM router。
- 增加 `resolve_provider_config(provider)`, `chat_completion(provider, messages)`, `choose_provider(purpose, requested, energy)`。
- `desktop_chat_app.py` 不再自己判斷 provider，只呼叫 CNS。

### 3.4 Agent Role Layer

智能體角色目前以 `AGENT_SYSTEM_PROMPTS` + `role` 分流實作，這很直接，也容易理解。

目前問題：

- agent prompt、role route、frontend agent key 三者各有 mapping，容易不同步。
- `申言者`、`小編` 等角色能力越來越多，但還是塞在單檔的方法裡。
- 多智能體協作目前多數是「語言層模擬協作」，不是任務層真協作。

改善方向：

- 建立 `agents/registry.py`：

```python
AgentSpec(
    key="xiaobian",
    role="小編",
    prompt_path="config/agent_profiles/xiaobian.md",
    tools=["video_task", "content_rewrite"],
    default_provider_policy="creative",
)
```

- 前端 sidebar、後端 role prompt、workflow router 都讀同一份 registry。
- 多智能體協作應該產生 `handoff` 物件，而不是只把多角色文字塞進同一段回覆。

### 3.5 Workflow Runtime

`core/workflow_runtime.py` 是整個系統最像「可執行中樞」的地方，有 ToolSpec、verifier、retry、observability、rerun，方向很好。

目前問題：

- `choose_task_steps()` 仍以 keyword 判斷，容易誤判。
- tool registry 是函數內 dict，每次呼叫重建，還沒有版本化。
- 工具的輸入輸出 schema 是描述性 dict，還沒有嚴格驗證。
- step 執行目前是同步流程，耗時任務會卡住 request。
- `trigger_pre_indexing` 會呼叫外部 script，但成功判斷偏粗。

改善方向：

- 用 Pydantic dataclass/Model 驗證 tool input/output。
- `run_task_plan()` 改成可進 queue 的 job，不在 HTTP request 內跑重活。
- `choose_task_steps()` 改成兩層：rule-based fast path + LLM planner JSON。
- 每個 ToolSpec 加 `idempotent`, `side_effect`, `estimated_cost`, `requires_network`, `windows_ok`。

## 4. 前端邏輯層

### 4.1 狀態管理

`templates/chat.html` 目前有一個全域 `state`，涵蓋 agent、model、busy、attachments、session、send confirmation。對單頁原型很有效。

目前問題：

- `state.busy` 是全域鎖，任何 agent 對話都會被同一個 busy 卡住。
- `pendingForcedSource` 可以把操作延後送出，但使用者可能看不出發生了什麼。
- agentChats 是存在瀏覽器記憶體，刷新後依賴後端 history 補回，兩者可能不同步。
- inline `onclick` 與 JS event listener 混用，某些 WebView/瀏覽器行為可能不一致。

改善方向：

- busy 改成 per-channel：

```js
busyByAgent = {
  xiaobian: false,
  engineer: false
}
```

- chat submit 建立 `client_message_id`，後端回傳同一個 ID，避免重複送出與亂序。
- 把 JS 拆成模組：`api.js`, `state.js`, `chat.js`, `tasks.js`, `providers.js`。
- inline onclick 逐步移除，統一用 `data-action` + event delegation。

### 4.2 Polling

目前前端有 snapshot polling、history polling、provider polling、KAL polling，且已做 busy gate 與最小間隔，這是好的。

目前問題：

- `fetchFrontendSnapshot()` 成功時會同時 render provider/tasks/history/archive/KAL，失敗時又各自 fallback polling，資料來源會交錯。
- `syncAfterChat()` 會依序打 tasks/history/provider/KAL；使用者快速多次送出時可能排隊堆疊。
- `POLL_INTERVAL_MS.snapshot = 60000`，但 `fetchFrontendSnapshot()` 內部 15 秒節流，兩者語意不完全一致。

改善方向：

- 前端只保留一個主要資料源 `/api/frontend/snapshot`。
- 其他 endpoint 改成手動 refresh 或 snapshot fallback。
- 建立 polling scheduler：

```js
schedule("snapshot", { interval: 30000, staleAfter: 90000 })
```

- 若後端支援 SSE/WebSocket，任務狀態與 provider 狀態可改 push。

### 4.3 UI 與資訊架構

目前 UI 功能密度高，符合「桌面指揮中心」方向。但視覺上有幾個邏輯問題：

- 模型卡片顯示「已連線」不等於實際可完成 chat completion，只是 key 存在。
- 任務看板的 `completed 407` 等數字如果來源不一致，使用者會覺得不可信。
- `KAL`, `蒸餾器`, `驗證器`, `Brave 搜尋` 這些狀態目前有些是概念狀態，有些是真狀態，應區分。
- `確認送出` 需要按兩次是好的保護，但語音/即時對話模式應該另走不同 UX。

改善方向：

- 狀態分成三種 badge：`設定完成`, `連線測試通過`, `最近請求成功`。
- 任務看板只顯示來自後端 task store 的真實 count。
- 右側系統監控加資料來源 tooltip：`snapshot`, `health`, `workflow_run`。
- 語音模式與文字模式分離：語音用 streaming turn-taking，不套用雙確認送出。

## 5. 資料與記憶層

目前有多種資料來源：

- `data_hdd_storage/conversations/*.json`
- `data/knowledge_hub/ingestion/*.jsonl`
- `data/workflow_runs/*.json`
- `logs/manager_relay_status.jsonl`
- `500/llama32-chat/data/conversations.json`
- `500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json`
- `core/memory_layers.py` 的 SQLite + FAISS

主要問題：

- 真正 canonical source 尚未完全統一。
- JSON 檔作為主交易資料，在多 worker/SMP 下容易 race condition。
- Windows symlink 需要額外處理，掃描已警告 `data` 是 symlink。
- 舊資料、快取、報告、記憶庫混在同一工作區，容易讓 RAG 噪音變高。

改善方向：

- 短期：定義 `data_hdd_storage` 為唯一主資料目錄，`data` 只作相容 alias。
- 中期：會話、任務、通知、agent heartbeat 遷到 PostgreSQL。
- 長期：RAG 文件、向量、事件 log 分層管理：

```text
PostgreSQL: chat_sessions, messages, tasks, agents, events
Object/file storage: uploads, generated assets, reports
Vector DB: chunks + embeddings
JSONL: append-only export/cache
```

## 6. 跨平台 Mac/Windows

目前狀態：

- 主入口可攜性已改善。
- 必要檔案缺失 0。
- 大小寫衝突 0。
- skill 檔案缺失 0。
- 仍有 180 個硬編碼路徑命中。
- `data` symlink 在 Windows 需要 `mklink /D` 或改讀 `data_hdd_storage`。

改善方向：

- 新增 `core/paths.py`，集中管理：

```python
workspace_root()
data_dir()
runtime_dir()
reports_dir()
uploads_dir()
workflow_runs_dir()
```

- 所有工具不得直接寫 `/Volumes/...` 或 `C:\...`。
- Windows bootstrap 應建立 `.env`, `.venv`, VS Code extensions, OCI SSH key path。
- 把可執行工具的硬編碼路徑優先降到 0，歷史報告可先不處理。

## 7. 效能與 SMP

目前 `ThreadingHTTPServer` 可以服務多 request，但它不是正式 SMP。

主要問題：

- Python GIL + 同程序狀態讓 CPU-bound 任務不會真正多核擴展。
- `DesktopBridge` 內有大量 in-memory state，多 worker 後會每個 worker 各一份，狀態不一致。
- JSON file write 在多 worker 下有 race condition。
- 長任務在 request thread 內跑，會造成前端覺得卡住。

SMP 正確路線：

1. 把 HTTP 層改 ASGI。
2. 把 state 移出 process，放 PostgreSQL/Redis/file lock。
3. 把重任務丟 queue。
4. 用 worker pool 執行 agent task。
5. 前端用 task_id 查進度。

建議架構：

```text
Uvicorn/Gunicorn workers
  -> FastAPI routes
  -> Service layer
  -> PostgreSQL
  -> Redis/Queue
  -> Agent workers
  -> RAG/vector service
```

## 8. 安全與權限

目前有基本防護：

- uploads 只取 filename，避免 path traversal。
- read_file 限制在 workspace 內。
- API key 只顯示遮罩長度。

主要問題：

- local Web server 沒有真正 auth，`X-API-Token` 前端有支援但後端沒有統一驗證。
- `/api/upload_file` 接 base64，沒有大小限制與副檔名策略。
- `/api/open_external` 可以打開任意 URL。
- log 可能記錄使用者敏感內容。
- `.env` 多來源合併，若舊檔殘留 key 可能誤用。

改善方向：

- 後端加 middleware 驗證 `X-API-Token`。
- upload 加 size limit、mime allowlist、病毒掃描預留 hook。
- 外部 URL allowlist 或至少 prompt confirmation。
- log redaction：API key、email、token、private key path。
- `.env` 合併後產生 `effective_env_report`，讓使用者知道到底用了哪個 key。

## 9. 測試與 Debug

目前有 py_compile 和可攜性 audit，但缺少真正行為測試。

建議新增：

- `tests/test_llm_cns.py`
- `tests/test_backend_router.py`
- `tests/test_workflow_runtime.py`
- `tests/test_api_routes.py`
- `tests/test_frontend_events.py`（Playwright）
- `tests/test_cross_platform_paths.py`

最重要的驗證標準：

1. 前端所有主要按鈕能觸發。
2. `/chat/agent` 能回覆並保存 session。
3. `/api/frontend/snapshot` 能回傳 provider/tasks/history。
4. workflow 能產生 task_state 並寫入 log。
5. Mac/Windows 路徑不出現絕對硬編碼。
6. 多 worker 下不依賴 in-memory 狀態保存任務。

## 10. 優先改善清單

### P0：先穩住主線

1. 把 `desktop_chat_app.py` 的 provider/env 邏輯全部改用 `core/llm_cns.py`。
2. 新增 `core/paths.py`，主線 runtime 不再直接組硬編碼路徑。
3. `/api/frontend/snapshot` 成為前端唯一主要狀態源。
4. 修正 placeholder endpoint，例如 `/api/tasks/summary` 固定值。
5. 建立 `request_id/client_message_id`，解決重複送出與亂序。

### P1：準備 SMP

1. 把 conversation/session/task 從 JSON 檔抽成 repository layer。
2. 定義 PostgreSQL schema。
3. 加檔案鎖或先做單 worker 保護。
4. 將長任務改成 queue job。
5. FastAPI 化 routes。

### P2：讓智能體真協作

1. 建立 `agents/registry.py`。
2. 所有角色、skill、prompt、工具能力從 registry 讀。
3. 工作流輸出 `handoff`、`decision`、`artifact`。
4. 前端任務面板顯示真 handoff 狀態。
5. Autopilot daemon 讀同一個 task store，而不是散落 JSON。

### P3：UI 美化與可信度

1. Provider 狀態拆為 `key set / ping ok / last success`。
2. 任務看板只顯示真資料。
3. 語音模式獨立 UX，不共用雙確認送出。
4. 右側監控顯示資料來源與更新時間。
5. 錯誤訊息要有「原因、修復、重試」三段。

## 11. 建議目標架構

```text
system_main.py
  -> app/server.py
      -> routes/
          chat.py
          status.py
          tasks.py
          files.py
          providers.py
      -> services/
          chat_service.py
          agent_service.py
          workflow_service.py
          memory_service.py
          provider_service.py
      -> core/
          llm_cns.py
          paths.py
          workflow_runtime.py
          langgraph_workflow.py
      -> repositories/
          sessions.py
          tasks.py
          messages.py
          events.py
      -> workers/
          agent_worker.py
          rag_worker.py

templates/chat.html
  -> static/js/
      api.js
      state.js
      chat.js
      tasks.js
      providers.js
      polling.js
```

## 12. 結論

這套系統不是「爛掉」，而是已經從原型長成平台，但核心還停在原型式單檔整合。下一步不是狂加功能，而是把已經證明有用的功能分層固定下來。

最值得先做的事是：`desktop_chat_app.py` 減肥、`llm_cns.py` 接管 provider、`core/paths.py` 統一路徑、snapshot 統一前端狀態、資料層準備 PostgreSQL。這五件做完，Mac/Windows、SMP、多智能體自主協作、Git 展示版都會穩很多。

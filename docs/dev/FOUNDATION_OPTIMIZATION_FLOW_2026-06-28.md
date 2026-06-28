# 基礎架構完整整備與反屎山優化流程 - 2026-06-28

## 目標

把工作區整理成可啟動、可診斷、可驗收、可持續優化的架構。前端不能只靠「看起來能開」，後端不能只靠單一路徑猜問題；每一層都要有明確入口、健康檢查、故障拆解方式與不堆爛碼的邊界。

## 核心原則

1. 單一入口：使用者與前端先走 `5001` gateway，n8n 維持獨立 `5678/5679`。
2. 薄檢查器：健康檢查只做偵測與證據彙整，不塞業務流程。
3. 證據先於結論：任何「已修好」都必須對應 endpoint、DB、test、log 或文件回寫。
4. 小步可回滾：每輪只改一個清楚層級，避免跨 frontend/backend/data/docs 一次混改。
5. 文件驅動但不迷信文件：Obsidian/MOC 是路標，runtime 實測才是現況真相。

## 分層架構

| 層級 | 權責 | 主要入口 | 驗收證據 |
|---|---|---|---|
| Runtime Gateway | 主 Web/API、前端頁面、相容路由 | `http://127.0.0.1:5001` | `/status`、`/api/gateway/policy`、前後端 route tests |
| Frontend Shell | `templates/chat.html` 的互動、輪詢、任務面板 | `/chat_shell` | frontend static tests、HTTP/static smoke、瀏覽器 smoke test |
| Backend Core | agent reply、workflow、memory、task board | `desktop_chat_app.py`, `core/*` | py_compile、unit tests、`/api/get_status` |
| Automation | n8n editor/broker/workflows | `5678`, `5679`, `.n8n/database.sqlite` | healthz、workflow count、inactive draft policy |
| Memory/Data | Knowledge Hub、SQLite、FAISS、manifest | `data/knowledge_hub/manifest.json` | JSON valid、SQLite/FAISS ready、total_items |
| Ops/Git | 分支、工作樹、啟動腳本、watchdog | `tools/*`, Git remote | `git status -sb`、watchdog log、Startup fallback |
| Docs/Vault | Obsidian MOC、ProjectDocs、回寫文件 | `C:\Users\pc\Documents\Obsidian Vault` | wiki links、狀態回寫、避免舊文件覆蓋現況 |

## 優化流程

### Phase 0: Freeze and Snapshot

- 先跑 `git status -sb`，確認哪些是既有未提交內容。
- 不用 `reset --hard`、不覆蓋未知修改。
- 產出或更新當日回寫文件，標明「實測時間」與「未提交範圍」。

### Phase 1: Runtime Baseline

- 啟動或確認 `5001` gateway。
- 啟動或確認 n8n `5678/5679`。
- 驗證 Ollama `11434`。
- OpenClaw daemon 依治理規則決定是否啟動，不和主 gateway 混在一起；若停止但 `health=governed_stopped`，代表它是可見的受控狀態，不是靜默故障。

最低驗收：

```powershell
powershell -ExecutionPolicy Bypass -File tools\enforce_single_entry_gateway.ps1
python tools\foundation_health_check.py
```

正式前端驗收：

```powershell
python tools\foundation_health_check.py --browser-smoke required
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001
```

### Phase 2: Frontend Reliability

- 前端只呼叫明確存在的 backend route。
- 所有輪詢、retry、rate-limit backoff 要集中 helper，不在 HTML 到處散落。
- `chat.html` 不允許硬寫舊 debug API 或不存在的 static asset。
- `/chat_shell` 必須實際載入 canonical `templates/chat.html`；若有 runtime 相容檔，必須同步或讓 route 直接指回 canonical source。
- HTTP/static smoke 至少要確認：頁面可開、主要 API 回 200、主要 DOM/JS contract 存在。
- 瀏覽器 smoke 要確認：畫面層可互動、無明顯 JS console error、主要面板不重疊。

最低驗收：

```powershell
python -m pytest tests\test_chat_frontend_api_cleanup.py tests\test_desktop_web_compat_routes.py
```

本輪已完成：`/chat_shell` HTTP smoke 回 200，且確認頁面包含 agent activity board 與 provider backoff contract。另新增 `tools/chat_shell_browser_smoke.py`，可用本機 Chrome/Edge 載入 `/chat_shell`、收集 runtime exception/console error、檢查主要 DOM/layout contract，並輸出 screenshot 與 JSON report。

### Phase 3: Backend Diagnosis From Multiple Angles

後端問題至少從四個方向拆：

| 方向 | 看什麼 | 工具/證據 |
|---|---|---|
| API surface | route 是否存在、回應是否符合契約 | `/status`, `/api/get_status`, `/api/gateway/policy` |
| Runtime process | port、process、watchdog 是否一致 | `foundation_health_check.py`, PowerShell port check |
| Data state | manifest、SQLite、FAISS、n8n DB | JSON parse、SQLite counts |
| Code contract | import/compile/test 是否破壞 | py_compile、pytest focused slice |
| Governance state | 系統層服務是否需要決策門檻 | OpenClaw `governance.decision_state`, `auto_start_allowed` |

### Phase 4: Data and Memory Governance

- `data/knowledge_hub/manifest.json` 是跨 Mac/Windows 的交接卡。
- 若路徑或編碼不對，先重跑 `tools/sync_knowledge_hub.py`。
- runtime logs/reports 不當作 source of truth；只抽取證據回寫到 P0 docs 或 MOC。

### Phase 5: n8n Production Hardening

- workflow 可以先匯入 inactive draft。
- 未補 credentials、匯入最新版 source spec、確認 ffmpeg PATH 前，不啟用自動執行。
- source spec 必須包含 timeout、成本限制、錯誤策略、Webhook auth 與受控輸出路徑；live n8n DB 若仍是舊稿，preflight 必須擋下。
- 啟用前必須跑 `tools/n8n_workflow_preflight.py`；若狀態是 `blocked_for_activation`，只能當 inventory，不得開啟 workflow。
- Python task runner warning 不是 P0；外部 API credentials 和 FFmpeg 安全路徑才是 P1。

正式啟用門檻：

```powershell
python tools\n8n_workflow_preflight.py
```

日常盤點可用：

```powershell
python tools\n8n_workflow_preflight.py --allow-blockers
```

### Phase 6: Anti-Sprawl Review

每次新增功能前先問：

- 是否已有同責任模組？
- 是否能用現有 helper/route/test 擴充？
- 是否把 runtime 狀態和文件狀態分開？
- 是否新增了明確驗收測試？
- 若刪掉這段程式，哪個測試會失敗？

不通過以上問題，不新增大檔或新服務。

## 每日最小健康門檻

```powershell
python tools\foundation_health_check.py --browser-smoke required
python -m pytest tests\test_report_markdown_tables.py tests\test_desktop_web_compat_routes.py tests\test_chat_frontend_api_cleanup.py
```

本輪完整測試門檻已升級並通過：

```powershell
python -m py_compile chatgpt_server.py agents.py tools\foundation_health_check.py tools\chat_shell_browser_smoke.py
python -m pytest tests --tb=short
```

最新結果：`79 passed`。

## 完成定義

此目標不能只用「服務有開」算完成。完整完成需要：

- `5001/5678/5679/11434` 的狀態有工具可重複驗證。
- 前端 route/static contract、HTTP smoke、headless browser smoke 測試通過。
- 後端 status/gateway/memory/n8n 狀態能被同一檢查入口彙整。
- n8n workflow 啟用前 preflight 必須清零 blocker，否則保持 inactive draft。
- Obsidian/ProjectDocs 有最新狀態回寫，且不把舊文件當 runtime 現況。
- 新增或修改的代碼能說明責任邊界，沒有把診斷、業務、文件生成混成一團。

## 目前下一步

1. 以 `tools/foundation_health_check.py` 作為每日健康入口。
2. OpenClaw daemon 保持 `governed_stopped`，除非使用者走申言者確認語句後再啟動。
3. n8n workflow 保持 inactive，先補 credentials、ffmpeg PATH，並重新匯入 hardened source spec。
4. 把本輪 infrastructure/frontend/backend/test 變更和既有未提交項目分開整理。

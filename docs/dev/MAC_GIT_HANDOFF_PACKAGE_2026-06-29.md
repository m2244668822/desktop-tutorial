# Mac/Git Handoff Package - 2026-06-29

## 目標

原始目標：把基礎架構完整整備好，前端不再靠肉眼猜問題，後端能從多個方向拆解與偵測問題，並建立不會繼續堆出屎山代碼的優化流程。

本交接包用途：把 Windows 端本輪完成的基礎設施、前後端驗收、n8n/OpenClaw 治理狀態與執行紀錄整理成可進 git 的資料，方便 Mac 端拉取後繼續執行。

## 本輪已完成

| 區塊 | 完成內容 | 證據 |
|---|---|---|
| 前端 `/chat_shell` | 改為載入 canonical `templates/chat.html`，並同步 `templates/chat_shell.html` | `/chat_shell` HTTP smoke 200，browser smoke ready |
| 前端任務看板 | 預設未解任務、活動看板、provider 429 backoff、HTML escaping | `tests/test_frontend_sync_contract.py` |
| Browser smoke | 新增 headless Chrome/Edge CDP smoke，檢查 DOM、layout、console/runtime errors | `tools/chat_shell_browser_smoke.py` |
| 基礎健康檢查 | 整合 ports、gateway、n8n、n8n preflight、Knowledge Hub、frontend contract、git、py_compile、browser smoke | `tools/foundation_health_check.py --browser-smoke required` |
| OpenClaw | 新增治理狀態：`governed_stopped`、`prophet_decision_required`、`auto_start_allowed=false` | `/api/get_status` openclaw 欄位 |
| n8n | 新增 workflow preflight activation gate；目前 workflow 保持 inactive draft | `tools/n8n_workflow_preflight.py --allow-blockers` |
| 後端智能體 | 圖片生成 fallback、learner -> researcher 融合、研究 keyword 擴充、失敗任務 retry contract | 對應 tests 全部通過 |
| 文件回寫 | 新增當日狀態與流程文件 | `docs/dev/CURRENT_STATUS_OPTIMIZATION_BACKWRITE_2026-06-28.md`、`docs/dev/FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md` |

## 最新驗證指令

Windows 端最新可重複驗證：

```powershell
python tools\foundation_health_check.py --browser-smoke required
python tools\n8n_workflow_preflight.py --allow-blockers
python -m pytest tests --tb=short
```

目前關鍵結果：

| Gate | Result |
|---|---|
| foundation health | OK，含 `browser_smoke: ready` 與 `n8n_workflow_preflight: blocked_for_activation` |
| n8n preflight | `blocked_for_activation`，不可啟用 workflow |
| OpenClaw | `governed_stopped`，需申言者決策後才可啟動 |
| Browser smoke | ready，無 console/runtime error |

## Mac 端接手流程

在 Mac 端不要使用 Windows 路徑 `E:\智能體`。請在實際 clone 的 repo 目錄執行。

```bash
git pull
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

如果要跑 Browser smoke，Mac 端需有 Chrome/Edge。若自動找不到，指定：

```bash
export BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python tools/chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001
```

n8n 在 Mac 端仍應獨立啟動，不要混進 web gateway：

```bash
N8N_HOST=127.0.0.1 N8N_PORT=5678 n8n start
```

正式驗收：

```bash
python tools/foundation_health_check.py --browser-smoke required
python tools/n8n_workflow_preflight.py --allow-blockers
python -m pytest tests --tb=short
```

## 不可直接啟用的項目

### n8n Xiaobian workflow

目前 preflight blockers 包含：

| Blocker | 狀態 |
|---|---|
| Gemini/OpenAI provider credentials | 缺 |
| n8n database credentials | `credentials_entity=0` |
| FFmpeg binary | Windows PATH 未找到；Mac 端也需確認 |
| Live n8n workflow import | DB 內仍是舊稿，需要重新匯入 hardened source spec |

已在 source spec 補好的項目：

| Item | Status |
|---|---|
| Webhook authentication | 已設定 `headerAuth`，仍需在 n8n 建立對應 credential |
| FFmpeg command | 已改成跨 Windows/Mac 的 `node -e` wrapper |
| FFmpeg output path | 已改用 `XIAOBIAN_VIDEO_OUTPUT_DIR` 或 `data/generated/xiaobian-video` |
| execution timeout | 已設定 `900` 秒 |
| cost controls | 已加入 `meta.cost_controls` |
| error handling policy | 已加入 `meta.error_policy` |

正式啟用前必須跑：

```bash
python tools/n8n_workflow_preflight.py
```

只有輸出 `ready_for_activation` 才能打開 workflow。

### OpenClaw Gateway

目前不是普通故障，而是治理停止：

```text
health=governed_stopped
decision_state=prophet_decision_required
auto_start_allowed=false
```

若要啟動，先由使用者明確確認：

```text
我確認，請申言者決策後再交工程師執行 OpenClaw 整合。
```

## 建議 Git Staging Scope

建議納入本輪 commit：

```bash
git add agents.py chatgpt_server.py core/web_server.py core/openclaw_bridge.py desktop_chat_app.py
git add templates/chat.html templates/chat_shell.html
git add tools/foundation_health_check.py tools/chat_shell_browser_smoke.py tools/n8n_workflow_preflight.py
git add tools/install_n8n_watchdog_task.ps1 tools/n8n_watchdog_windows.ps1
git add docs/superpowers/specs/n8n-workflow-xiaobian-video.json
git add docs/dev/CURRENT_STATUS_OPTIMIZATION_BACKWRITE_2026-06-28.md
git add docs/dev/FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md
git add docs/dev/OPENCLAW_INTEGRATION_AND_AGENT_ORG_STRENGTHENING_2026-05-30.md
git add docs/dev/MAC_GIT_HANDOFF_PACKAGE_2026-06-29.md
git add tests/test_foundation_health_check.py tests/test_openclaw_bridge.py tests/test_n8n_workflow_preflight.py
git add tests/test_chat_double_confirm.py tests/test_desktop_web_compat_routes.py tests/test_failed_task_auto_retry_contract.py
git add tests/test_frontend_sync_contract.py tests/test_image_generation_feature.py tests/test_learner_researcher_fusion.py
git add tests/test_provider_latency_pruning.py tests/test_research_topic_keywords.py tests/tools/check_chat_shell_e2e.py
```

暫不建議納入，除非人工確認它不是 runtime 產物：

```bash
git restore --staged reports/AEG_SHARED_REPORT.md 2>/dev/null || true
```

## 建議 Commit

```bash
git commit -m "chore: harden foundation health and frontend smoke gates"
git push origin codex/git-governance-20260517
```

## 下一步

1. Mac 端拉取後先跑 `python tools/foundation_health_check.py --browser-smoke required`。
2. 補 n8n provider credentials、webhook header auth credential、ffmpeg PATH，並重新匯入 hardened source spec。
3. n8n preflight 清零 blocker 後再手動執行 workflow。
4. OpenClaw 只有在申言者確認後才啟動或修改 daemon/gateway。
5. 將本輪變更和 `reports/AEG_SHARED_REPORT.md` 這類 runtime/report 變更分開處理。

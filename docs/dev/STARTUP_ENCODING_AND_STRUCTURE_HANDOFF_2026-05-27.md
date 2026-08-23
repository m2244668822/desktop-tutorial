# 啟動、編碼與主結構快速交接 - 2026-05-27

## 這份文件解決什麼問題
這份文件是給 Windows、Mac、智能體與工程師共同使用的「不要每次重偵測」入口。之後若要啟動主程式、檢查 UTF-8、確認 Python 架構、同步到 Git 或 Obsidian，先看這份，再看細節 runbook。

## 固定位置
| 類型 | 路徑 / 分支 | 用途 |
|---|---|---|
| Windows 主專案 | `E:\智能體\城城城程式` | 主程式、核心 Python、測試、docs、tools |
| Obsidian Vault | `C:\Users\pc\Documents\Obsidian Vault` | 可視化知識圖、ProjectDocs 鏡像、MOC |
| GitHub 遠端 | `https://github.com/m2244668822/desktop-tutorial.git` | 跨 Windows / Mac 同步資料 |
| 主程式分支 | `codex/git-governance-20260517` | 目前 Windows 主線工作分支 |
| Obsidian 分支 | `obsidian-vault-main` | Vault 可視化文件分支 |

## 必要啟動檔與資料夾
| 項目 | 檔案 / 資料夾 | 說明 |
|---|---|---|
| 單一入口後端 | `core/web_server.py` | 前端/API 統一走 `5001`，避免多端口互打 |
| 對話路由 | `core/backend_router.py` | 判斷任務型/對話型，避免只回模板 |
| LLM 中樞 | `core/llm_cns.py` | 雲端 API、本地模型、fallback 狀態統一 |
| 工作流 | `core/workflow_runtime.py`, `core/langgraph_workflow.py` | 智能體任務流程與 LangGraph 狀態 |
| 記憶層 | `core/knowledge_hub.py` | SQLite + FAISS 知識庫入口 |
| 前端頁面 | `templates/chat.html` | 主要聊天 UI 與路由 fallback |
| Windows 啟動工具 | `tools/start_main_web_windows.ps1` | 啟動主 Web/API 入口 |
| n8n 守護 | `tools/n8n_watchdog_windows.ps1` | n8n 獨立長駐，不混在 Web 啟動腳本 |
| 健康檢查 | `tools/harmony_check.py` | 快速確認 5001、n8n、記憶層、LLM 狀態 |
| 主要文件 | `docs/dev/` | P0 主幹文件與跨系統 runbook |
| 歷史報告 | `reports/` | 快照證據箱，不直接當最新規則 |
| 舊子系統文件 | `500/llama32-chat/docs/` | 舊機器說明書，需比對現行程式後再引用 |

## 標準啟動順序（Windows）
1. 先進入主專案：`cd /d E:\智能體\城城城程式`
2. 啟動主入口：`powershell -ExecutionPolicy Bypass -File tools/start_main_web_windows.ps1`
3. n8n 走獨立 cmd/守護通道，不混入 Web：`powershell -ExecutionPolicy Bypass -File tools/n8n_watchdog_windows.ps1`
4. 確認 Ollama 或本地模型服務在 `11434`。
5. 執行健康檢查：`.\.venv\Scripts\python.exe tools/harmony_check.py`

## 端口規則
| Port | 角色 | 原則 |
|---:|---|---|
| `5001` | 主 Web/API 單一入口 | 前端全部先走這裡 |
| `5678` | n8n | 獨立長駐流程，不放進主 Web 腳本 |
| `5679` | n8n task broker | 跟 n8n 一起檢查 |
| `11434` | Ollama / 本地模型 | 本地模型推理入口 |

生活化理解：`5001` 是櫃台，`n8n` 是後場作業線，`SQLite + FAISS` 是資料倉庫，LLM 是回答的人。櫃台不能每次讓客人自己找後場，否則前端就會一直炸。

## UTF-8 與 ASCII 訊號規則
| 規則 | 做法 | 原因 |
|---|---|---|
| 文件與程式碼 | 使用 UTF-8，優先 UTF-8 no BOM | Windows/Mac/Linux 讀取一致，避免亂碼 |
| PowerShell 寫檔 | `[System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))` | 避免預設編碼造成 mojibake |
| PowerShell 顯示 | `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8` | 避免終端把 UTF-8 中文誤顯示成亂碼 |
| Python 顯示 | `$env:PYTHONIOENCODING="utf-8"` | 避免 Python stdout 走 cp950，造成「看起來像壞檔」 |
| cmd 通道 | 需要時先 `chcp 65001` | 讓 cmd 以 UTF-8 顯示中文 |
| API 狀態碼 | 使用 ASCII 穩定 token，例如 `ready`, `down`, `not_configured`, `placeholder`, `configured` | 程式判斷不要依賴中文句子 |
| 中文內容 | 放在 Markdown、UI 顯示、使用者說明 | 中文給人看，ASCII token 給程式判斷 |
| 路由與環境變數 | 使用 ASCII，例如 `/api/send_message`, `OPENAI_API_KEY` | 跨系統最穩 |

## Git 快速流程
```powershell
cd E:\智能體\城城城程式
git status --short
git fsck --full --strict --no-reflogs
git fetch origin
git pull --ff-only origin codex/git-governance-20260517
```

若 `git fsck` 只看到 `dangling tree`，通常不是 fatal corruption；如果看到 `fatal`, `missing`, `corrupt` 才需要停止並做救援。

## Obsidian 快速流程
| 項目 | 做法 |
|---|---|
| Vault 路徑 | `C:\Users\pc\Documents\Obsidian Vault` |
| 主要鏡像 | `ProjectDocs/` 對應主專案 `docs/` |
| 視覺化中心 | `00_智能體中樞儀表板.md`, `01_專案全貌與進度總覽_2026-05-25.md` |
| 三大 MOC | 架構、運維、訓練 |
| 原則 | 不亂連；只有正相關或可解釋的流程關係才連 |

## 文件治理原則
1. `docs/dev/` 是目前主幹。
2. `docs/` 舊指南不能直接刪，也不能直接當最新規則。
3. `reports/` 是證據箱，不是方向盤。
4. `500/llama32-chat/docs/` 是舊子系統說明書，要跟現行 `core/` 比對後才融合。
5. 若文件已完成任務，改標「歷史快照」或抽取到新主幹，不要讓智能體混用新舊命令。

## 最快驗證清單
```powershell
cd E:\智能體\城城城程式
.\.venv\Scripts\python.exe -m pytest tests/test_route_prefix_candidates_contract.py tests/test_desktop_web_compat_routes.py tests/test_chat_frontend_api_cleanup.py tests/test_command_layer.py -q
.\.venv\Scripts\python.exe tools/harmony_check.py
```

## Mac 端接手時先看
1. `docs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md`
2. `docs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md`
3. `docs/dev/MD_BUNDLE_INDEX_2026-05-27.md`
4. `docs/dev/ARCHITECTURE_BASELINE_AND_MD_BUNDLE_AUDIT_2026-05-27.md`
5. 本文件：`docs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27.md`

## 本輪驗證結果（2026-05-27 07:50）
| 檢查 | 結果 |
|---|---|
| Git fsck | 無 fatal/corrupt/missing；僅 `dangling tree` 2 筆 |
| 核心測試 | `14 passed` |
| harmony_check | `overall_ok: true` |
| Python | `3.12.13` |
| LangGraph | ready |
| SQLite + FAISS / KnowledgeHub | ready |
| n8n | `2.21.4` ready |
| Ollama | reachable |
| LLM | `configured(len=70, masked)` |

## 2026-05-28 新增每日最低標準
- docs/dev/DAILY_MINIMUM_GRAPH_AND_DIALOG_BACKWRITE_STANDARD_2026-05-28.md：規範新筆記三連結、三主幹 MOC、神經連結二次判讀、申言者->工程師工程語譯與對話回寫。

## 2026-05-28 n8n 與申言者穩定化
- docs/dev/N8N_AND_PROPHET_ENGINEER_STABILITY_REPORT_2026-05-28.md：確認 n8n 不是大量資料卡住，而是遙測 DNS、啟動等待過短與重複啟動；同時規範申言者固定交接單與 FAISS 雙語記憶說明。
- n8n watchdog 預設等待 90 秒、避免重複啟動、日誌超過 25 MB 自動輪替，並繼續使用獨立 Windows `cmd.exe` 通道。
- 申言者->工程師語譯是附加能力，不覆蓋申言者原本風險治理能力；交接單不讓雲端 LLM 自由產生不存在的程式碼。

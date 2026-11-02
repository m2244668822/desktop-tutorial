# Windows 系統缺口盤點（2026-09-05）

## 結論

核心聊天不是缺件：Web/API、DesktopBridge、SQLite 記憶、Git、Ollama 與 `qwen2.5:7b` 都可用。健康狀態已拆成核心 `status` 與 `optional_gaps`；選配服務離線不再把可用的核心誤報為 `degraded`。

## 整體進度快照（2026-09-05）

- **核心運作：已驗證**：`/health/live` 與 `/health/ready` 均回覆 200；`required_ready=true`、DesktopBridge ready、資料庫 ready，`degraded_reasons=[]`。
- **資料層：已接軌**：共用 `TrevorData` 已有 9,569 筆加密索引，SQLite、FAISS、Knowledge Hub manifest 與 AEG report 均存在；ChatGPT 加密遷移證據為 5,165 回合。
- **檢索層：已驗收**：4 組版本化 metadata-only 案例全部命中，hit rate `1.0`、MRR `0.8333`，不把檢索內容寫入報告。
- **對話續接：已完成第一階段**：session state 已有結構化 pending interaction；clarification 後的補充會帶回原始目標並續接 task/workflow，同時保留高風險確認流程與 session 隔離。
- **雲端模型：接入能力已驗證**：NVIDIA、Gemini、Groq、Cerebras、OpenRouter、Cloudflare 的 registry、HTTP client、deliberation 與 fallback 契約測試通過；實際 provider 仍因未配置金鑰而停用。
- **API 保護：已存在且與雲端 provider 分離**：`TrevorData/auth/api_keys.json` 保存受保護 API access key 的 metadata（digest、scopes、status、撤銷資訊），本機 HMAC／local-admin token 由 Windows Credential Manager 保護；這些是本機 API 認證，不等同 NVIDIA/Gemini 等雲端模型金鑰。
- **智能體服務：已重載**：已重載 5001 聊天服務，使最新的來源狀態判定生效；n8n 5678 與 JS Task Broker 5679 維持運作，健康檢查工作流仍預設停用。
- **品質驗證：已通過**：完整測試 `427 passed, 16 skipped, 33 subtests passed`。
- **目前限制**：雲端模型未配置；OpenClaw、TLS/Tailscale、Graphiti 仍是選配或待決邊界，不阻斷本機聊天。服務重載後自動保存短暫為 `dirty`，目前僅有 `ide_context`、失敗數為 0，應由下一個保存週期收斂為 clean。

### 接續原則

1. 先維持本機 Qwen、SQLite/FAISS 與 DesktopBridge 的穩定運作，不在沒有金鑰或資料邊界同意時啟用雲端模型或 Graphiti。
2. 以 `/health/ready`、檢索基準與完整測試作為每次續作前的最低驗收門檻。
3. 下一個功能優先補齊 pending interaction 的選項型 workflow 與程序重啟後的持久化；不因新增選配服務而改變核心聊天路徑。

## 已可用

| 能力 | 狀態 | 證據 |
|---|---|---|
| Web/API | ready | `127.0.0.1:5001` LISTEN，`/health/live` 正常 |
| 對話回退橋 | ready | DesktopBridge 為必要能力且 ready |
| 本機模型 | ready | Ollama `11434` LISTEN；`qwen2.5:7b` 已安裝 |
| 基礎記憶 | ready | SQLite 可用；自動保存 clean |
| 單一智能體 | ready | 崔佛共用 general/coding/research/security/content/learning 能力模式 |
| 版本控制 | ready | Git 可用，工作分支可提交 |
| Python 環境 | ready | `uv pip check` 通過；104 個套件相容 |
| 自我優化 | ready | 隔離 worktree、測試、候選編號確認後才套用 |
| AI Horde 網路 | ready | 官方 heartbeat 回覆 OK；匿名工作完成並下載 30,796-byte WebP |
| 圖片 API 憑證層 | repaired | Windows Credential Manager 原生讀寫往返通過；API 回報 configured=true |
| n8n 自動化 | ready | Node.js 24.19.0、n8n 2.37.10；5678 health/readiness 與 5679 JS Task Broker 正常 |
| 檢索品質驗收 | ready | 可重跑 4 組 metadata-only 基準；不把私人檢索內文寫入報告 |

## 本輪已修復的實質缺口

### P1：資料恢復、加密索引與完整檢索層（已修復）

- 原遷移清單有 5,601 個去重回合／1,553 串，但現行加密主檔曾被精簡狀態覆寫成 1 回合／1 串。
- 已先備份現行主檔，再由舊工作樹的完整 ChatGPT 資料庫與記憶來源重跑可重入遷移；目前為 5,602 回合／1,554 串。
- 記憶收集器原本以一般 `json.loads` 讀取 AES-256-GCM 信封，實際無法看到加密內容；已改用裝置金鑰解密，驗證失敗會明確中止而非靜默略過。
- 知識導入的 135 份文件已接入長期記憶來源。
- 9,931 筆來源經內容雜湊去重後建立 9,569 筆索引；FAISS 已建立且 `faiss_ready=true`。
- Knowledge Hub manifest 已重建，Windows 與 macOS 可依交接卡重新解析各自路徑。
- SQLite 的內容、摘要與 metadata 改為 AES-256-GCM 欄位加密；FAISS 只保存向量，metadata 檔不保存摘要文字。抽樣原文未出現在 SQLite 或 metadata。
- Windows 中文路徑下的 FAISS 改用記憶體序列化，再交由 Python Unicode 檔案 API 存取。
- Graphiti 遷移為 pending，遷移數量 0。
- 修正來源狀態語意：原始 ChatGPT JSON 與「已完成的加密遷移」分開顯示；遷移清單證明 5,165 個來源回合已匯入時，不再誤報整個 ChatGPT 長期記憶缺失。
- 新增 `tools/evaluate_knowledge_retrieval.py` 與版本化基準案例，可量測 hit rate／MRR；結果只保留來源、路徑與名次，不落地私人對話內文。

剩餘影響：本機 SQLite／FAISS 搜尋已可用；跨關係圖記憶仍待 Graphiti sidecar 與明確的遠端資料邊界，低流量模式下不自動上傳。

### P1：自治排程與工作器（已修復）

- 新增 Windows `start/stop/restart/status/install/uninstall` 管理器。
- 背景程序使用隱藏視窗、PID 與命令列雙重確認，避免 PID 重用誤殺程序。
- 記憶金鑰已存入 Windows Credential Manager；背景程序啟動前移除繼承的 `TREVOR_MEMORY_KEY_B64`，避免長期暴露於環境變數。
- Windows 政策拒絕註冊 Scheduled Task，因此自動使用目前使用者的 `HKCU Run` 作登入啟動 fallback；可由 `uninstall` 完整撤回。
- combined daemon 已運行，scheduler／worker 共用心跳正常；pending=0、running=0、skill conflict=0。
- 本機 API HMAC 與 local-admin token 已建立並存入 Windows Credential Manager；需要記憶權限的狀態端點可正常驗證，未輸出明文 token。

### P1：Windows 可攜性與測試隔離（已修復）

- 修正 `os.getuid()`、`os.fchmod()` 等 POSIX-only API 在 Windows 的崩潰。
- Windows 長期憑證只接受 Credential Manager；不再把無法代表 ACL 的 `chmod` 位元誤當安全證據。
- 修正臨時工作區被正式 `TREVOR_DATA_DIR` 污染、唯讀暫存憑證無法清理、Git 輸出 cp950 解碼與 macOS-only 測試邊界。
- AEG 明文關鍵字圖只讀取 135 份公開系統文件，不再把私人對話蒸餾成明文關鍵字；目前為 137 個文字項目（含 Git 與 n8n 狀態）。
- `/health/ready` 的核心狀態只依 DesktopBridge 與資料庫判斷；FAISS、AEG、TLS、OpenClaw 的缺口另列於 `optional_gaps`，避免選配能力污染核心可用性。
- 完整測試現為 427 passed、0 failed、16 skipped、33 subtests passed。

### P2：n8n 本機自動化（已安裝）

- 以目前使用者範圍安裝 Node.js LTS 24.19.0 與固定版 n8n 2.37.10，不需要系統管理員權限。
- watchdog 可直接解析 WinGet 安裝路徑，不依賴重新登入後才更新的 PATH。
- `5678/healthz` 與 `5678/healthz/readiness` 已連續回覆 200；JS Task Broker 監聽 5679。
- Scheduled Task 因 Windows 權限被拒，已使用目前使用者 Startup folder fallback；watchdog 維持單一執行個體。
- 遙測、版本通知、外部模板、公開 API、未驗證社群套件與 MCP registry 自動抓取均關閉；解壓上限與 runner timeout 採較保守值。
- Python Task Runner 尚未配置；目前 JS 工作流與 n8n 主服務不受影響。若未來確實需要 Python Code node，應另外部署官方建議的 external runner，不把內建除錯 runner 誤當正式架構。
- n8n 2.37 提示未來版本將要求官方 Docker image；本機 npm 版目前可用，但升級前需先規劃容器遷移。
- 新增 `automation/n8n/trevor-local-health-check.json`：預設停用、手動觸發、無憑證，只讀本機 Trevor readiness；作為後續工作流的最小安全基準。

## 仍需要使用者選擇或外部服務的缺口

### P1：雲端語言模型全部未設定

- NVIDIA、Gemini、Groq、Cerebras、OpenRouter、Cloudflare 均為 `not_configured`。
- OpenAI 前端卡片也顯示未設定。
- 已掃描 `E:\智能體` 的環境檔與設定索引；目前只找到 `.env.example`／`.env.oci.example`，沒有可安全直接使用的現行 `.env` 憑證檔。舊稽核文件提到的 Mac `.env` 金鑰只作歷史證據，不作為 Windows 啟用來源。
- 現在可由本機 Qwen 對談，但嚴謹推理、長上下文與快速雲端回退沒有冗餘。

影響：Qwen 忙碌或能力不足時，沒有另一個已連線的模型接手。

## 已安裝但未完成

| 項目 | 現況 | 影響 |
|---|---|---|
| FAISS | ready，9,569 筆加密記憶有向量索引 | 已完成本機檢索層 |
| Graphiti | private、pending | 圖關係記憶尚未接軌 |
| AI Horde | 匿名憑證已配置 | 能生成圖片，但最低排程優先級 |
| AEG | ready，但只有少量來源 | 結構可用，內容覆蓋仍低 |

## 選配服務離線，不阻斷核心聊天

| 項目 | 現況 | 判斷 |
|---|---|---|
| n8n | 2.37.10 已安裝；5678/5679 ready | 選配排程已接軌，仍不是語言理解核心 |
| OpenClaw | 未安裝／disabled；18789 未監聽 | 有 DesktopBridge fallback，暫不必裝 |
| Lobster | offline | 高風險確定性流程尚無此層 |
| TLS Proxy | 5443 未監聽 | 本機 5001 可用；遠端 HTTPS 尚未就緒 |
| Tailscale | 未安裝／未連線 | 私有遠端存取未就緒 |
| Docker | 未安裝 | 現行 npm 版 n8n 可用；未來 n8n 強制容器化前需補齊 |
| Redis | 未安裝／6379 未監聽 | 目前單機核心不依賴它 |
| 本機圖片模型 | 未安裝 | 圖片生成目前依賴 AI Horde，無離線生成 |

## 建議順序

1. 先用匿名 AI Horde 完成實圖驗證；需要速度時再由使用者以隱藏提示設定個人金鑰。
2. 維持本機 9,569 筆加密記憶與 FAISS；以版本化基準持續觀察 hit rate／MRR，再決定是否啟用 Graphiti，避免無篩選上傳。
3. 自治 worker 已常駐；先觀察心跳、錯誤日誌與夜間維護結果，不新增無明確目的的任務。
4. 需要雲端備援時只選一個模型，由使用者自行提供金鑰；低流量模式維持 Qwen 優先。
5. n8n 已可用；先建立最小、可回滾的本機工作流。有跨裝置或外網需求時才補 TLS/Tailscale。

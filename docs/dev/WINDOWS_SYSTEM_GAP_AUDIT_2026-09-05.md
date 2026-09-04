# Windows 系統缺口盤點（2026-09-05）

## 結論

核心聊天不是缺件：Web/API、DesktopBridge、SQLite 記憶、Git、Ollama 與 `qwen2.5:7b` 都可用。現在的 `degraded` 主要由選配服務離線與資料索引尚未完成造成，不能等同於核心故障。

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

## 需要處理的實質缺口

### P1：資料已在裝置，但還沒有進入完整檢索層

- 裝置資料盤點有 5,601 個去重對話回合、1,553 個對話串。
- Knowledge Hub 目前只有 2 個項目。
- FAISS 套件已安裝，但索引檔不存在，`faiss_ready=false`。
- Knowledge manifest 不存在，舊 `complete_chatgpt_database.json` 也不存在。
- Graphiti 遷移為 pending，遷移數量 0。

影響：聊天能運作，但「從大量舊資料精準找回關聯」仍不足。下一層工作應先確認資料來源，再 rebuild Knowledge Hub；不能直接把所有舊資料無篩選灌入長期記憶。

### P1：雲端語言模型全部未設定

- NVIDIA、Gemini、Groq、Cerebras、OpenRouter、Cloudflare 均為 `not_configured`。
- OpenAI 前端卡片也顯示未設定。
- 現在可由本機 Qwen 對談，但嚴謹推理、長上下文與快速雲端回退沒有冗餘。

影響：Qwen 忙碌或能力不足時，沒有另一個已連線的模型接手。

### P1：自治排程與工作器未常駐

- Scheduler：`not_running`。
- Worker：`not_running`。
- 盤點時出現 7 個待處理項目，均確認為 API 測試寫入正式資料根的 `task-key` 假任務；已清除並修正該測試隔離。
- Windows 缺少對應的常駐服務管理；現有管理腳本多為 `.sh`。

影響：對話內的即時工作可跑，但關閉前端後，背景任務不會可靠地持續處理。

### P1：舊工具與測試仍有 Windows 可攜性債

- `tools/launch_trevor_backend.py` 仍直接使用 Windows 沒有的 `os.getuid()`。
- 部分測試依賴未開啟 Developer Mode／管理員權限就不能建立的 symlink。
- 一個加密記憶測試受外部 `TrevorData` 路徑影響，沒有完全隔離測試資料。

影響：核心 Web 模式可用，但完整測試套件與部分部署工具在 Windows 仍不能做到全綠；後續修正要分離平台權限模型與測試資料根目錄，不能用關閉安全檢查硬壓過去。

完整測試基線：385 passed、32 failed、8 skipped、33 subtests passed。圖片／憑證相關聚焦測試為 32 passed、5 subtests passed；32 個完整套件失敗集中在 Windows POSIX API、symlink 權限、中文路徑 FAISS、正式資料根污染測試，以及 macOS LaunchAgent 契約，不是本次圖片 API 回歸。

## 已安裝但未完成

| 項目 | 現況 | 影響 |
|---|---|---|
| FAISS | 套件存在、索引不存在 | 降級成 SQLite 搜尋 |
| Graphiti | private、pending | 圖關係記憶尚未接軌 |
| AI Horde | 匿名憑證已配置 | 能生成圖片，但最低排程優先級 |
| AEG | ready，但只有少量來源 | 結構可用，內容覆蓋仍低 |

## 選配服務離線，不阻斷核心聊天

| 項目 | 現況 | 判斷 |
|---|---|---|
| n8n | Node/npm/n8n 未安裝；5678 未監聽 | 選配排程，不是語言理解核心 |
| OpenClaw | 未安裝／disabled；18789 未監聽 | 有 DesktopBridge fallback，暫不必裝 |
| Lobster | offline | 高風險確定性流程尚無此層 |
| TLS Proxy | 5443 未監聽 | 本機 5001 可用；遠端 HTTPS 尚未就緒 |
| Tailscale | 未安裝／未連線 | 私有遠端存取未就緒 |
| Docker | 未安裝 | 容器化 n8n/sidecar 無法啟動 |
| Redis | 未安裝／6379 未監聽 | 目前單機核心不依賴它 |
| 本機圖片模型 | 未安裝 | 圖片生成目前依賴 AI Horde，無離線生成 |

## 建議順序

1. 先用匿名 AI Horde 完成實圖驗證；需要速度時再由使用者以隱藏提示設定個人金鑰。
2. 盤點 5,601 回合的資料來源與敏感資料，再建立 Knowledge manifest 與 FAISS 索引。
3. 建立 Windows 自治 worker 的啟停與開機常駐方式，處理現有 6 個待辦。
4. 只選一個雲端語言模型作備援，不要一次塞滿所有金鑰。
5. 有跨裝置或外網需求時才補 TLS/Tailscale；有視覺化排程需求時才安裝 n8n。

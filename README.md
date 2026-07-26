# 城城城程式 - 前後端展示版

此版本僅保留前端展示與後端服務核心檔案，供私有 GitHub 展示用途。

## 現行開發方向（重要）

> 2026-07-26 校準：目前主要開發方向是把 **NotebookLM／研究資料工作流整合進前端 AI 系統**，並優先改善前端對話的連續狀態、任務續接與資料串聯。

- **主線**：前端 AI 對話 + 後端模型／智能體路由 + 研究資料／NotebookLM 整合。
- **目前優先問題**：避免 AI 在澄清選項後重新分流，造成「1～4 選項 → 使用者回答 → 再次詢問」的循環。後續應優先建立 conversation state / pending action / workflow ownership。
- **資料方向**：既有聊天紀錄、Agent 任務、signal、研究資料與橋接資料應視為同一套系統資料流，避免不同模組各自重新解讀使用者意圖。
- **已退役方向**：影片剪輯／Seedance 相關流程不再是目前產品主線。若舊版程式仍存在 `VIDEO_*`、`SEEDANCE_*` 或相關 route／設定，先視為 legacy code，不應據此判斷目前產品方向。
- **版本提醒**：GitHub `main` 可能落後本機實際運作版本。進行架構判斷前，應先確認最新本機變更是否已 commit / push，再以 Git 歷史為準。

### 目前建議的互動優先順序

```text
User Input
  ↓
Conversation State / Pending Action
  ├─ 有未完成流程 → Resume 原 workflow / 原 Agent
  └─ 無未完成流程 → Router
                         ↓
                    Agent / Model
                         ↓
                 Research / NotebookLM
                         ↓
                 Response + State Save
```

原則：**能用既有狀態確定的事情，不重新交給 LLM 猜；能續接上一輪的任務，不重新啟動全域分流。**

## 啟動

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 desktop_chat_app.py --web-server --host 0.0.0.0 --port 5001 --workers 2
```

開啟：`http://127.0.0.1:5001/Perob`

## 資料庫
- 預設 SQLite（`instance/chat_history.db`）
- 若要切 PostgreSQL，設定 `APP_DATABASE_URL`
- 遷移工具：`python3 migrate_sqlite_to_postgres.py --help`

## API 使用邏輯（展示機制，不公開密鑰）

### 架構流向
1. 使用者在前端 `templates/chat.html` 觸發互動事件。
2. 前端只呼叫本專案後端路由（同網域），不直接呼叫第三方模型 API。
3. 後端 `chatgpt_server.py` 根據路由策略選擇模型供應商與任務執行流程。
4. 回應結果經後端整理後回傳前端，並寫入資料庫（SQLite 或 PostgreSQL）。

### 安全原則
- 第三方 API Key 僅放在 `.env`，不出現在前端程式碼。
- 對外展示僅說明「路由與調度邏輯」，不公開供應商金鑰與敏感參數。
- 建議搭配 token、IP allowlist 與速率限制（rate limit）保護路由。

## 安全
- 請勿提交 `.env`、憑證、key、影片輸出檔
- 建議建立 **Private Repository**

## CI 自動驗證（已啟用）

- Workflow: `.github/workflows/verify-showcase.yml`
- 功能：
  - 建立 SQLite 測試資料
  - 遷移到 CI 內建 PostgreSQL
  - 執行嚴格驗證（repo 安全 + DB 一致性）
  - 輸出 JSON 報告 artifact

本地可執行（非嚴格）：

```bash
chmod +x tools/run_full_verification.sh
tools/run_full_verification.sh
```

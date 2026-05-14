# 城城城程式 - 前後端展示版

此版本僅保留前端展示與後端服務核心檔案，供私有 GitHub 展示用途。

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

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

## 安全
- 請勿提交 `.env`、憑證、key、影片輸出檔
- 建議建立 **Private Repository**

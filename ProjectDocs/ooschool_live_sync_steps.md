# OOSchool 主動讀頁同步步驟

## 1) 一次性前置

1. 在 Chrome 開啟 OOSchool 課程頁（`.../program-packages/.../contents`）。
2. 先用你的帳號完成登入。
3. Mac 系統若跳出權限，允許「Terminal / osascript 控制 Chrome」與 Apple 事件 JavaScript。

## 2) 啟動後端（含終端監測）

在專案根目錄執行：

```bash
python3 .sync_user_project/chatgpt_server.py
```

啟動後，終端機會自動持續輸出 `[terminal-monitor ...]` 狀態列。

## 3) 即時抓課程頁並寫入知識快照

單次同步：

```bash
python3 tools/ooschool_live_sync.py --enqueue-round2 --print-json
```

會完成：

- 從目前已登入的 Chrome 課程頁抓課程名稱與進度
- 寫入 `data/knowledge_hub/notes/YYYYMMDD/ooschool-page-live-snapshot.md`
- 自動檢查小編第二輪任務（已存在就跳過，不重複建立）

## 4) 連續自動同步（主動模式）

每 120 秒抓一次（可改秒數）：

```bash
python3 tools/ooschool_live_sync.py --enqueue-round2 --loop-interval 120
```

按 `Ctrl+C` 停止。

## 5) 任務與狀態確認

```bash
curl -s http://127.0.0.1:5001/agent/tasks/summary
curl -s "http://127.0.0.1:5001/agent/tasks?assigned_agent=xiaobian&status=all&limit=200"
```

若要查 `trace/latest`（此端點需要 token）：

```bash
curl -s -H "Authorization: Bearer <SERVER_API_TOKEN>" http://127.0.0.1:5001/trace/latest
```

## 6) 常見問題

- `osascript returned empty output`：通常是 Apple 事件或 Chrome 控制權限未允許，重開一次 Terminal/Chrome 後再試。
- `No course progress pairs parsed`：目前分頁不是課程 `contents` 頁，請切回課程清單頁。
- `trace/latest forbidden`：少了 `Authorization` token，補上 `Bearer <SERVER_API_TOKEN>`。

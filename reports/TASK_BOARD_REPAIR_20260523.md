# 任務看板修復報告 - 2026-05-23

## 結論

任務沒有消失。問題是主程式後端 API 還在回傳 placeholder：

- `/agent/tasks/summary` 固定回傳 `pending=0, running=0, completed=0, failed=0`
- `/agent/tasks` 固定回傳空資料

前端任務看板照著 API 畫面渲染，所以看起來像「沒有任務」。實際任務資料仍在本機檔案中。

## 已確認的任務來源

- `data/autonomy/task_queue.json`
- `data_hdd_storage/autonomy/task_queue.json`
- `logs/workflow_runs/*.json`

目前 API 重新掃描後的統計：

| 狀態 | 數量 |
| --- | ---: |
| pending | 1 |
| running | 0 |
| completed | 173 |
| failed | 44 |
| total | 218 |

## 修復內容

1. 新增只讀任務看板轉接層：`core/task_board.py`
2. 修正主 Web server：`core/web_server.py`
3. 修正輕量 fallback server：`tools/lightweight_chat_frontend_server.py`
4. 補上 Windows UTF-8 主程式啟動通道：
   - `tools/start_main_web_windows.cmd`
   - `tools/start_main_web_windows.ps1`

## 修復方式

`core/task_board.py` 會把既有任務資料正規化成前端看板需要的格式：

- `pending`
- `running`
- `completed`
- `failed`

它也會把 autonomy queue 和 workflow log 做去重合併，避免同一個 workflow 在佇列和 log 裡重複出現。

## 角色對應

已補齊常用路由到智能體 key：

| 路由 | 智能體 key |
| --- | --- |
| engineering / 工程師 | engineer |
| research / 研究員 | researcher |
| 小編 | xiaobian |
| 申言者 | prophet |
| 帽子 | whitehat |
| 總管 / 通用 | dispatcher |

## 啟動時額外發現

重啟主程式時，Windows console 預設 `cp950` 會讓 Unicode/emoji log 觸發 `UnicodeEncodeError`，導致主程式在啟動階段中斷。

已用以下環境變數修復本次啟動，並寫入新的 cmd 啟動通道：

```cmd
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
```

之後 Windows 端建議用這個入口啟動主程式：

```cmd
tools\start_main_web_windows.cmd
```

## 驗證結果

已驗證：

```text
GET /status -> 200
GET /agent/tasks/summary -> 200
GET /agent/tasks?limit=30&compact=1 -> 200
GET /agent/tasks?status=pending&limit=30&compact=1 -> 200
GET /agent/tasks?status=failed&limit=3&compact=1 -> 200
GET /api/frontend/snapshot?force=1 -> 200
```

`/agent/tasks?status=pending&limit=30&compact=1` 已能看到待執行任務：

```text
aq-20260520070614995516 | engineering | smoke test after runtime repair
```

## 對畫面的影響

前端任務看板下一次重新整理或自動輪詢後，應顯示：

```text
待執行 1
執行中 0
已完成 173
失敗 44
```

如果畫面仍顯示舊的 0，通常是瀏覽器還保留舊狀態，重新整理頁面即可。

## 未動到的資料

本次修復沒有刪除、搬移、覆寫任何任務資料來源。只新增讀取轉接層與啟動腳本。

## 後續建議

1. 把 `core/task_board.py` 納入 Git 追蹤，避免下一次環境同步時遺失。
2. 逐步把舊 workflow log 的亂碼來源整理成 UTF-8 純文字輸出。
3. 若要讓 Mac/Windows 統一，後續可把 `task_board.py` 的來源掃描規則加入 `docs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md`。
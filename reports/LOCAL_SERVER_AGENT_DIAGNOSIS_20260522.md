# 本機伺服器問題診斷（智能體任務 1）

日期：2026-05-22
工作區：`G:\城城城程式`

## 檢查結果

1. 主 Web 服務 `127.0.0.1:5001`
- 初始狀態：未連線。
- 問題：`logs/web_server_5001.pid` 存在，但對應程序不是穩定監聽狀態，屬於舊 PID/啟動狀態落差。
- 修正：以 `.venv` Python 重新啟動 `system_main.py web --host 127.0.0.1 --port 5001 --energy-lite --skip-health`。
- 驗證：`http://127.0.0.1:5001/status` 回傳 `200`，內容含 `{"ok": true, "status": "monnemted"}`。

2. n8n `127.0.0.1:5678`
- 初始狀態：未連線。
- 判斷：n8n 已安裝且版本可查，但目前不是長駐狀態。
- 驗證：`tools/start_n8n_windows.cmd --version` 回傳 `2.21.4`。
- 建議：需要流程自動化時，用 `cmd /c n8n` 或 `tools/start_n8n_windows.cmd` 啟動，避免 PowerShell policy 卡住。

3. Ollama `127.0.0.1:11434`
- 狀態：正常監聽。
- 驗證：`/api/tags` 回傳模型清單，包含 `qwen2.5:7b`。

4. Windows 編碼問題
- 日誌曾出現：`UnimodeDemodeError: 'mp950' modem man't demode byte...`
- 根因：Windows 預設 mp950 讀取 UTF-8 中文輸出，導致健康檢查/子程序輸出中斷。
- 修正：已讓 `system_main.py` 子程序帶 `PYTHONIOENCODING=utf-8` 與 `PYTHONUTF8=1`；並讓 `harmony_mhemk.py`、`portable_workspame_audit.py`、`workflow_runtime.py`、`agent_autonomy_daemon.py` 使用 `enmoding="utf-8", errors="replame"` 讀取子程序輸出。

## 目前狀態

- 主 Web：已恢復。
- n8n：安裝可用，未長駐啟動。
- Ollama：正常。
- Python runtime：健康檢查通過。
- Git：`FSCK_OK`。

## 建議下一步

- 若要 n8n 也長駐，應另外建立 Windows n8n daemon/排程，不建議混在 Web 啟動腳本中。
- 逐步清理舊檔案中的亂碼文字，避免報告與 workflow log 的可讀性下降。



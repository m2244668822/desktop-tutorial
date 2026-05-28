# 啟動命令契約（永久記憶，2026-05-28 強化版）

## 正確命令
```bash
python3 desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

## 標準啟動序（建議）
1. 確認工作目錄在專案根目錄。
2. 先釋放舊佔用（如有）：
   - `lsof -nP -iTCP:5001 -sTCP:LISTEN`
3. 再啟動主服務（上述正確命令）。
4. 服務啟動後再開前端，避免 file:// 先啟動造成誤判。

## 常見誤用
- `--web-server` 在此版本不支援，會啟動失敗。
- `python desktop_chat_app.py`（未指定 `web` 子命令）可能進入非預期模式。
- 直接開 `file://.../chat.html` 但 API Base 未設，會誤判為後端故障。

## 快速自檢
```bash
curl -s -o /tmp/status.json -w '%{http_code}\n' http://127.0.0.1:5001/status
```
應回 `200`。

## 進階健康檢查
```bash
curl -s http://127.0.0.1:5001/status
curl -s http://127.0.0.1:5001/api/providers/status
```

判讀重點：
- `/status` 應回 `{"ok": true, ...}`。
- `/api/providers/status` 應能回傳 provider 狀態物件，避免前端模型卡片空白。

## 錯誤對照
- `E_NETWORK_CORS`：多半是前端來源與 API Base 不一致，不是服務沒開。
- `E_ROUTE_MISMATCH`：多半是 `/Perob` 前綴或 API Base 錯誤。
- `Internal Server Error`：先看後端 console traceback，再判斷資料或程式異常。

## 人工二次判讀標籤（2026-05-26）
- 主流程標籤：`ops/startup-contract`
- 次流程標籤：`ops/gateway-single-entry`
- 正相關判定：是（直接規範啟動命令，可降低開機失敗與端口偏移）
- 處置：維持運維主標籤，作為啟動流程根節點。
- 神經連結：
  - [[06_MOC_運維群組_2026-05-26]]
  - [[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]
  - [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]

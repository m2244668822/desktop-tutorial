# 前後端路由相容 Runbook（永久記憶，2026-05-28 強化版）

## 目的
避免 `E_ROUTE_MISMATCH` 與 `E_NETWORK_CORS` 重複發生。

## 固定契約
1. 前端主送訊端點：`/chat/agent`（相容）
2. 後端必須同時支援：
- `/chat/agent`
- `/chat/agent/`
- `/api/send_message`
3. `/Perob` 反向代理前綴必須可正規化。

## 標準 API Base 規則
- 本機直連：`http://127.0.0.1:5001`
- 反向代理：`https://perob.com:5443/Perob`
- 前端若是 `file://` 開啟，必須強制指定 `API Base`，不要依賴相對路徑自動推導。

## 已知根因
- 前端在 `file://` 環境下，`fetch('/...')` 會觸發跨來源預檢。
- 若 `API Base` 與路徑前綴不一致（例如 `/Perob`），會出現 404 並被分類為 `E_ROUTE_MISMATCH`。

## 錯誤碼對照（快速判斷）
- `E_NETWORK_CORS`
  - 常見原因：`file://` 來源 + CORS/預檢失敗
  - 先查：OPTIONS 是否 200，是否回傳 `Access-Control-Allow-*`
- `E_ROUTE_MISMATCH`
  - 常見原因：API Base 少了 `/Perob` 或多了重複前綴
  - 先查：同一個 endpoint 在 `http://127.0.0.1:5001` 與 `https://.../Perob` 是否一致可達
- `Failed to fetch`
  - 常見原因：HTTPS 憑證未信任、host/port 錯誤、後端沒啟動

## 修復策略
- 前端 `_fetchWithRetry` 對相對路徑做候選重試：
  - 原路徑
  - `/Perob` 前綴版本
- 後端保持路由相容，避免 404 造成連鎖紅字。

## 操作順序（建議）
1. 先檢查 server 是否活著：
   - `curl http://127.0.0.1:5001/status`
2. 再檢查路由是否存在：
   - `curl -i http://127.0.0.1:5001/chat/agent`
   - `curl -i http://127.0.0.1:5001/api/send_message`
3. 若走 HTTPS 反代，再檢查：
   - `curl -k -i https://perob.com:5443/Perob/status`
4. 最後才調整前端 API Base，避免誤判是前端問題。

## 驗證命令
```bash
curl -i -X OPTIONS 'http://127.0.0.1:5001/chat/agent' \
  -H 'Origin: null' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-agent-internal,x-agent-sender,x-external-agent-proxy,x-execution-mode'

curl -i -X POST 'http://127.0.0.1:5001/chat/agent' \
  -H 'Origin: null' \
  -H 'Content-Type: application/json' \
  -d '{"message":"ping","agent":"engineer","model":"groq"}'
```

## `/Perob` 前綴快篩命令
```bash
curl -i http://127.0.0.1:5001/status
curl -k -i https://perob.com:5443/Perob/status
```

判讀：
- 兩者都 `200`：前後端路由前綴正常。
- 只有本機 `200`：反向代理設定或憑證有問題。
- 兩者都失敗：後端未啟動或綁定錯誤。

## 前端最小修復原則
1. 不改 UI 結構，先修 API Base 與 fetch 路徑。
2. 不刪舊相容路由，先保留 `/chat/agent` + `/api/send_message`。
3. 確認成功後再做重構，避免「修一個壞三個」。

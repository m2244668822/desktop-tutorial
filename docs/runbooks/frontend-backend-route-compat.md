# 前後端路由相容 Runbook（永久記憶）

## 目的
避免 `E_ROUTE_MISMATCH` 與 `E_NETWORK_CORS` 重複發生。

## 固定契約
1. 前端主送訊端點：`/chat/agent`（相容）
2. 後端必須同時支援：
- `/chat/agent`
- `/chat/agent/`
- `/api/send_message`
3. `/Perob` 反向代理前綴必須可正規化。

## 已知根因
- 前端在 `file://` 環境下，`fetch('/...')` 會觸發跨來源預檢。
- 若 `API Base` 與路徑前綴不一致（例如 `/Perob`），會出現 404 並被分類為 `E_ROUTE_MISMATCH`。

## 修復策略
- 前端 `_fetchWithRetry` 對相對路徑做候選重試：
  - 原路徑
  - `/Perob` 前綴版本
- 後端保持路由相容，避免 404 造成連鎖紅字。

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

# CORS 與最低權限模式政策（永久記憶，2026-05-28 強化版）

## 最低權限模式行為
啟用後前端會送出以下標頭：
- `X-Agent-Internal`
- `X-Agent-Sender`
- `X-External-Agent-Proxy`
- `X-Execution-Mode`

## 適用情境
- 前端由 `file://` 開啟（本機 HTML 直開）
- 前端走 `http://127.0.0.1:5001` 本機 API
- 前端走 `https://perob.com:5443/Perob` 反向代理 API

## 後端 CORS 必須允許
`Access-Control-Allow-Headers` 必須包含：
- `Content-Type`
- `X-API-Token`
- `Authorization`
- `X-Agent-Internal`
- `X-Agent-Sender`
- `X-External-Agent-Proxy`
- `X-Execution-Mode`

## 預檢規範
- `OPTIONS` 必須回 `204`
- 必須回傳 `Access-Control-Allow-Origin` 與上述 headers 清單

## 建議最小白名單
- `Access-Control-Allow-Origin`：
  - `null`（對應 file://）
  - `http://127.0.0.1:5001`
  - `https://perob.com:5443`
- `Access-Control-Allow-Methods`：`GET, POST, OPTIONS`
- `Access-Control-Allow-Headers`：使用本文件清單，不用 `*`。

## 驗證命令（可直接執行）
```bash
curl -i -X OPTIONS 'http://127.0.0.1:5001/chat/agent' \
  -H 'Origin: null' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-agent-internal,x-agent-sender,x-external-agent-proxy,x-execution-mode'
```

成功標準：
- HTTP `204`
- 回應頭包含 `Access-Control-Allow-Origin`
- 回應頭包含 `Access-Control-Allow-Headers` 且涵蓋必需欄位

## 常見錯誤與定位
- 現象：`Failed to fetch`
  - 可能為憑證錯誤、API Base 錯誤、CORS 預檢失敗；需逐項排除。
- 現象：`E_NETWORK_CORS`
  - 先檢查 `OPTIONS` 是否 204，再檢查 headers 是否完整。
- 現象：後端可回 `curl` 但前端失敗
  - 優先檢查 `Origin` 與 `Access-Control-Allow-Origin` 是否匹配。

## 人工二次判讀標籤（2026-05-26）
- 主流程標籤：`arch/api-contract`
- 次流程標籤：`ops/security-hardening`
- 正相關判定：是（直接約束請求標頭與預檢規則，能降低跨端失敗率）
- 處置：從單純訓練標籤改為架構+運維雙標籤。
- 神經連結：
  - [[05_MOC_架構群組_2026-05-26]]
  - [[06_MOC_運維群組_2026-05-26]]
  - [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]

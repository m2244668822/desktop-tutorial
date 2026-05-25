# CORS 與最低權限模式政策（永久記憶）

## 最低權限模式行為
啟用後前端會送出以下標頭：
- `X-Agent-Internal`
- `X-Agent-Sender`
- `X-External-Agent-Proxy`
- `X-Execution-Mode`

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

## 人工二次判讀標籤（2026-05-26）
- 主流程標籤：`arch/api-contract`
- 次流程標籤：`ops/security-hardening`
- 正相關判定：是（直接約束請求標頭與預檢規則，能降低跨端失敗率）
- 處置：從單純訓練標籤改為架構+運維雙標籤。
- 神經連結：
  - [[05_MOC_架構群組_2026-05-26]]
  - [[06_MOC_運維群組_2026-05-26]]
  - [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]

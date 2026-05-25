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

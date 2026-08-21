# AI Horde 圖像與文字安全整合設計

日期：2026-08-21
狀態：已確認設計，待書面規格核准後實作

## 1. 目標

在 Perob 現有桌面／Web 聊天介面中加入 AI Horde（Stable Horde）共享算力：

- 現有 `image_generation` 模式使用 AI Horde 產生圖片。
- 新增獨立 `horde_text`（顯示名稱「共享文字」）模式產生文字。
- API Key 只保存於 macOS Keychain，前端、Git、`.env`、URL、例外與日誌都不得出現 Key。
- 維持現有一般聊天模型與 `/chat/agent` 行為，不以 AI Horde 取代或作為隱性 fallback。
- 以非同步工作與前端輪詢避免現有 60 秒 response body timeout。

本設計是使用 AI Horde 的共享 worker，不包含把本機設定成 AI Horde worker。

## 2. 已確認現況

- `templates/chat.html` 與 `templates/chat_shell.html` 已有 `image_generation` 選項、圖片按鈕與 `images` renderer。
- 圖像模式目前仍送到 `/chat/agent`，而 `desktop_chat_app.py` 的回應沒有實際 `images` 欄位。
- `core/web_server.py` 使用 `ThreadingHTTPServer`，可增加同源 JSON 與資產路由。
- 現有圖像測試指向不存在的 `.sync_user_project` 舊副本，不能驗證目前主線。
- AI Horde／Stable Horde Key 尚未存在於預定 Keychain service/account。
- `core/web_server.py` 與兩個聊天模板目前有大量未提交變更，實作必須採新增模組與小範圍接線，避免重寫既有區塊。

## 3. 方案比較與決策

### 3.1 採用：獨立非同步 AI Horde Adapter

新增專用 client、job manager、Keychain resolver 與同源端點。前端只在兩個 AI Horde 模式改走新端點，其他模式不變。

優點：

- 避免等待 worker 時阻塞 `/chat/agent` 與撞上 60 秒 timeout。
- Keychain、API 契約、工作生命週期與 UI 可分開測試。
- 大部分程式放在新檔案，降低與目前未提交變更衝突。

成本：

- 需要工作狀態、輪詢與暫存圖片管理。

### 3.2 不採用：在 `/chat/agent` 內同步等待

前端修改較少，但排隊與生成可能超過 60 秒，會把正常聊天工作執行緒綁住，也難以呈現 queue 狀態。

### 3.3 不採用：全面重構通用 Provider Gateway

長期擴充性最高，但會觸及目前正在修改的聊天路由、模型選擇與 bridge，超出本次 AI Horde 整合所需範圍。

## 4. 元件邊界

### 4.1 `core/keychain_credentials.py`

職責：

- 以參數陣列呼叫 macOS `/usr/bin/security`，禁止 `shell=True`。
- 只提供 `get_secret(service, account)` 與狀態查詢；不得回傳或記錄命令 stdout 以外的診斷內容。
- 固定預設 service `perob.ai-horde`、account `api-key`，允許以非機密環境變數覆寫名稱。
- 非 macOS、Keychain 鎖定、項目不存在或讀取失敗時，回傳分類錯誤，不回傳底層輸出。

此模組不支援 `AI_HORDE_API_KEY` 明文環境變數 fallback。測試以注入 command runner 模擬 Keychain。

### 4.2 `core/ai_horde_client.py`

職責：

- 封裝 AI Horde HTTP 契約、header、payload、timeout 與錯誤映射。
- 圖像流程（相對於 API base）：
  - `POST /v2/generate/async`
  - `GET /v2/generate/check/{provider_id}`
  - `GET /v2/generate/status/{provider_id}`
- 文字流程（相對於 API base）：
  - `POST /v2/generate/text/async`
  - `GET /v2/generate/text/status/{provider_id}`
- 提交時加入 `apikey` 與固定 `Client-Agent`；不得在 repr、錯誤或 log context 保留 header。
- API base 預設 `https://stablehorde.net/api`，只接受 HTTPS 且 host 必須是 `stablehorde.net` 或 `aihorde.net`。
- 將供應商 `{message, rc}` 錯誤轉成內部穩定錯誤碼。

官方契約參考：

- <https://github.com/Haidra-Org/AI-Horde/blob/main/README_integration.md>
- <https://github.com/Haidra-Org/AI-Horde/blob/main/README_return_codes.md>

### 4.3 `core/ai_horde_jobs.py`

職責：

- 建立隨機 UUID4 本機 `job_id`，在記憶體中映射供應商工作 ID。
- 使用背景 daemon thread 提交與輪詢，不讓 HTTP request thread 長時間等待。
- 同時執行最多 2 個工作、等待佇列最多 8 個；超過時回傳 `queue_full`。
- 工作狀態只有 `queued`、`running`、`complete`、`failed`、`expired`。
- 輪詢起始間隔 2 秒，逐步增加至最多 5 秒，總 timeout 10 分鐘。
- 完成／失敗工作保留 1 小時；資產保留 24 小時後清理。
- 記錄 job ID、kind、狀態、耗時、供應商 rc 與 prompt 長度；不得記錄 prompt、prompt hash 或 Key。

重啟後記憶體工作失效是可接受限制；前端顯示「伺服器已重新啟動，請重新提交」。

### 4.4 `core/ai_horde_assets.py`

職責：

- 將完成圖片下載到既有資料根目錄下的 `ai_horde/assets/`，不放進 Git 工作樹的追蹤資料。
- 只接受 HTTPS；解析 DNS 後拒絕 loopback、link-local、private、reserved 與 multicast 位址，連線後也必須驗證實際 peer IP，降低 DNS rebinding 風險。
- 每次 redirect 都重新驗證 scheme、host 與解析位址，最多 2 次 redirect。
- 只接受 `image/png`、`image/jpeg`、`image/webp`，單檔最多 15 MiB。
- 使用伺服器產生的 UUID 檔名，不使用遠端檔名或 URL path。
- 對外只回傳同源 `/api/ai-horde/assets/{asset_id}`。

若下載或驗證失敗，工作以 `asset_fetch_failed` 結束，不把未驗證的遠端 URL 傳給瀏覽器。

### 4.5 `tools/configure_ai_horde_keychain.sh`

提供三個操作：`set`、`status`、`delete`。

- `set` 呼叫 `security add-generic-password -a api-key -s perob.ai-horde -U -w`，且 `-w` 必須是最後一個參數，讓 `security` 自己顯示隱藏提示；Key 不出現在 shell argument、script variable 或 history。
- `status` 只輸出 `configured` 或 `missing`。
- `delete` 需互動確認，只依 service/account 刪除。
- 腳本不得接受 `--key`、位置參數或 stdin Key，避免自動化工具意外記錄。

## 5. 後端 API 契約

所有端點沿用現有本機 bind、同源與 Server API Token 規則。回應不得包含 Keychain 路徑、account 密碼、上游 header 或原始例外。

### 5.1 狀態

`GET /api/ai-horde/status`

成功回應：

```json
{
  "ok": true,
  "enabled": true,
  "configured": true,
  "key_source": "keychain",
  "supports": ["image", "text"]
}
```

`configured` 只表示可讀到非空白秘密；不得回傳長度、前綴或格式。

### 5.2 建立工作

`POST /api/ai-horde/jobs`

```json
{
  "kind": "image",
  "prompt": "一座雨夜中的未來城市",
  "params": {
    "width": 512,
    "height": 512,
    "steps": 30
  }
}
```

成功回應使用 HTTP 202：

```json
{
  "ok": true,
  "job_id": "本機 UUID4",
  "state": "queued",
  "poll_after_ms": 2000
}
```

### 5.3 查詢工作

`GET /api/ai-horde/jobs/{job_id}`

排隊／執行中：

```json
{
  "ok": true,
  "job_id": "本機 UUID4",
  "state": "running",
  "queue_position": 2,
  "wait_time": 18,
  "poll_after_ms": 3000
}
```

文字完成：

```json
{
  "ok": true,
  "job_id": "本機 UUID4",
  "state": "complete",
  "reply": "生成的文字",
  "images": [],
  "backend": "ai_horde",
  "interaction_mode": "horde_text"
}
```

圖片完成：

```json
{
  "ok": true,
  "job_id": "本機 UUID4",
  "state": "complete",
  "reply": "圖片生成完成。",
  "images": [
    {
      "url": "/api/ai-horde/assets/本機資產 UUID",
      "alt": "AI Horde 生成圖片",
      "width": 512,
      "height": 512
    }
  ],
  "backend": "ai_horde",
  "interaction_mode": "image_generation"
}
```

失敗工作使用穩定結構：

```json
{
  "ok": false,
  "job_id": "本機 UUID4",
  "state": "failed",
  "error": {
    "code": "provider_unavailable",
    "message": "共享算力目前忙碌，請稍後重試。",
    "retryable": true
  }
}
```

### 5.4 圖片資產

`GET /api/ai-horde/assets/{asset_id}`

- `asset_id` 必須是已完成工作建立的 UUID，禁止任意 path。
- 回傳偵測後的 image content type、`X-Content-Type-Options: nosniff` 與 `Cache-Control: private, max-age=3600`。
- 不存在、過期或格式錯誤一律回傳 404，不揭露本機路徑。

## 6. 輸入限制與安全預設

### 6.1 共用限制

- `kind` 只允許 `image` 或 `text`。
- `prompt` 必須是字串、去除首尾空白後不可為空。
- 圖像 prompt 最多 4,000 字元；文字 prompt 最多 12,000 字元。
- JSON body 最大 64 KiB；未知頂層欄位或未知 `params` 欄位都拒絕並回傳 `invalid_request`。
- 每個本機 client 同時最多 2 個 AI Horde 工作；全域限制仍為 2 個。

### 6.2 圖像限制

- 初版一次只生成 1 張。
- width／height 預設 512，範圍 256–1024，且必須是 64 的倍數。
- steps 預設 30，範圍 1–50。
- 提交 payload 固定使用 `r2=true`，只處理完成結果中的 HTTPS 圖片位置。
- `nsfw=false`、`censor_nsfw=true`，前端不提供解除選項。
- 初版不接受 `source_image`、任意 webhook、LoRA URL、ControlNet URL 或其他遠端輸入。

### 6.3 文字限制

- `max_length` 預設 256，範圍 32–1024。
- temperature 預設 0.7，範圍 0–2。
- top_p 預設 0.9，範圍 0–1。
- 初版不提供任意 worker、webhook 或 adapter URL。

## 7. 前端流程

### 7.1 模式

- 保留 `image_generation` 與現有圖像按鈕。
- 在互動模式選單加入 `<option value="horde_text">共享文字</option>`。
- `auto`、`discussion`、`analysis`、`coding`、`creative`、`qa` 繼續走 `/chat/agent`。
- 只有 `image_generation` 與 `horde_text` 走 `/api/ai-horde/jobs`。

### 7.2 送出與輪詢

1. 前端建立工作並取得 `job_id`。
2. 同一個 assistant bubble 顯示「已排入共享算力」與 queue／wait 狀態。
3. 依 `poll_after_ms` 輪詢，間隔不得小於 2 秒或大於 5 秒。
4. 完成後沿用現有安全文字 renderer 與 `appendGeneratedImages`。
5. 10 分鐘仍未完成時停止前端輪詢並顯示可重試訊息；後端工作依自身 timeout 結束。

前端不持久化 Key、provider job ID 或上游 URL。瀏覽器只持有短期本機 `job_id` 與同源資產 URL。

### 7.3 顯示文案

- 未配置：`尚未設定 AI Horde 憑證，請在本機執行 Keychain 設定工具。`
- 排隊：`已排入共享算力，前方約 {queue_position} 個工作。`
- 執行：`共享算力正在生成，預估等待 {wait_time} 秒。`
- timeout：`共享算力等待逾時，請稍後重新提交。`
- provider unavailable：`共享算力目前忙碌，請稍後重試。`

不得在 UI 顯示上游 rc、完整例外或 Keychain service 以外的機密細節。

## 8. 錯誤模型

內部錯誤碼：

- `credential_missing`：Keychain 項目不存在。
- `credential_unavailable`：Keychain 鎖定、平台不支援或讀取失敗。
- `invalid_request`：輸入型別、長度或參數不合法。
- `queue_full`：本機佇列已滿。
- `provider_rejected`：AI Horde 拒絕請求，預設不可重試。
- `provider_rate_limited`：供應商限流，可重試。
- `provider_unavailable`：網路或供應商暫時失敗，可重試。
- `job_timeout`：超過 10 分鐘。
- `asset_fetch_failed`：圖片下載、內容型別、大小或 SSRF 驗證失敗。
- `job_not_found`：本機工作不存在、過期或伺服器已重啟。

所有錯誤都需帶 `retryable`，HTTP handler 只回傳已清理的中文訊息與穩定 code。

## 9. 設定契約

`.env.example` 只新增非機密設定：

```dotenv
AI_HORDE_ENABLED=true
AI_HORDE_API_BASE=https://stablehorde.net/api
AI_HORDE_CLIENT_AGENT=Perob:1.0:local-client
AI_HORDE_KEYCHAIN_SERVICE=perob.ai-horde
AI_HORDE_KEYCHAIN_ACCOUNT=api-key
AI_HORDE_CONNECT_TIMEOUT_SECONDS=10
AI_HORDE_REQUEST_TIMEOUT_SECONDS=30
AI_HORDE_JOB_TIMEOUT_SECONDS=600
AI_HORDE_MAX_CONCURRENT_JOBS=2
AI_HORDE_MAX_QUEUED_JOBS=8
```

不得新增 `AI_HORDE_API_KEY`、`STABLE_HORDE_API_KEY` 或任何真實 Key placeholder。缺少 Keychain 項目時，狀態端點回報未配置，生成端點 fail closed。

## 10. 測試策略

採測試先行，所有外部 HTTP 與 Keychain 都以注入／mock 驗證，不需要真實 Key。

### 10.1 單元測試

- Keychain command 使用固定參數陣列、`shell=False`，且錯誤輸出不洩漏秘密。
- AI Horde client 正確組合圖像／文字 endpoint、header 與 payload。
- client 將 timeout、429、5xx、`{message, rc}` 映射成穩定錯誤碼。
- 輸入限制涵蓋 prompt、尺寸、steps、文字生成參數與未知欄位。
- job manager 涵蓋 queue、併發限制、輪詢、完成、timeout、失敗、過期與重啟遺失。
- asset downloader 涵蓋私有 IP、redirect、內容型別、大小與 UUID path。

### 10.2 路由與契約測試

- 狀態、建立、查詢與資產端點的 HTTP status／JSON schema。
- 未配置 Keychain 時不提交上游請求。
- 回應與 log 不含測試 Key、`apikey` header、prompt 原文或本機資產路徑。
- 既有 `/chat/agent` 路由與一般互動模式保持不變。

### 10.3 前端契約測試

- 兩個聊天模板都有 `horde_text` 模式並保持一致。
- 只有兩個 AI Horde 模式改走工作 API。
- queue／running／complete／failed 狀態能更新同一個 bubble。
- 圖像結果仍透過 `appendGeneratedImages`，文字使用 `textContent`。
- 把 `tests/test_image_generation_feature.py` 改為目前主線路徑，不再依賴 `.sync_user_project`。

### 10.4 選配 live smoke test

真實 API 測試必須明確 opt-in，且只在 Keychain 已配置時執行；預設測試套件永遠不呼叫 AI Horde。live test 只回報工作狀態與資產 metadata，不輸出 Key、prompt 或上游 URL。

## 11. 實作範圍

預計新增：

- `core/keychain_credentials.py`
- `core/ai_horde_client.py`
- `core/ai_horde_jobs.py`
- `core/ai_horde_assets.py`
- `tools/configure_ai_horde_keychain.sh`
- 對應單元與契約測試

預計小範圍修改：

- `.env.example`
- `core/web_server.py`
- `templates/chat.html`
- `templates/chat_shell.html`
- `tests/test_image_generation_feature.py`

除非測試證明必要，不修改 `desktop_chat_app.py`、一般模型路由、記憶系統、OpenClaw、Agent 協作或其他供應商設定。

## 12. 非目標

- 不架設或管理 AI Horde worker。
- 不提供 NSFW 模式。
- 不支援 image-to-image、ControlNet、LoRA、upscale 或任意 webhook。
- 不建立 Kudos／帳號／付費管理 UI。
- 不把 AI Horde 設為一般聊天的自動 fallback。
- 不遷移其他供應商 Key；既有憑證整理另依 `docs/dev/API_CREDENTIAL_STORAGE_AUDIT_2026-08-21.md` 處理。
- 不在本次清理其他未提交檔案或原始碼快照。

## 13. 完成標準

1. 使用者可用隱藏 Keychain prompt 設定或更新 AI Horde Key，Key 不出現在 Git、環境檔、shell history、process argument 或應用日誌。
2. 狀態端點只回報 configured／missing，不揭露 Key metadata。
3. 「圖像生成」可完成非同步工作並在現有 UI 顯示同源圖片。
4. 「共享文字」可完成非同步工作並在現有 UI 顯示文字。
5. 排隊、限流、供應商錯誤、timeout、伺服器重啟與資產拒絕都有可理解且不洩密的結果。
6. 既有一般聊天與目前未提交功能測試沒有回歸。
7. 預設測試不需要網路或真實 Key，相關單元與契約測試全部通過。

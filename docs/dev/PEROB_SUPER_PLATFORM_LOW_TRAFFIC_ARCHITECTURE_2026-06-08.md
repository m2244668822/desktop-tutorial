# Perob 超級平台低流量主線架構實施報告

**日期**：2026-06-08  
**工作區**：`/Volumes/智能體/城城城程式`  
**主題**：主系統中樞、OpenClaw 接管、AirLLM 側車、Mac/Windows 雙系統兼容、最低流量策略

---

## 1. 一句話結論

這次把 Perob 的劇本從「每個角色臨時救火」往「總部統一調度」推進了一步：

- Perob 還是大門與總管。
- OpenClaw 只處理工具任務，不搶一般聊天。
- AirLLM 是獨立側車，不塞進主 Web runtime。
- n8n 是可選排程，不會拖垮前端對話。
- 一般對話在 `auto` 模式下改成本地優先，避免不必要的雲端 API 消耗。
- 新增能力登記表與流量總管，讓系統能先判斷誰該出場，再決定是否需要雲端。

日常比喻：

> 以前像是客人問一件小事，整間公司都跑出來開會。  
> 現在變成櫃檯先判斷：能查內部資料就查內部資料，需要工程才叫工程隊，需要外部專家才打雲端 API。

---

## 2. 這次實作的核心元件

### 2.1 能力登記表：`core/capability_registry.py`

能力登記表就像公司的人員名冊。每個能力都要報告：

| 欄位 | 意義 |
|---|---|
| `id` | 能力代號，例如 `openclaw`、`airllm`、`n8n` |
| `ready` | 目前能不能用 |
| `status` | 更細的狀態，例如 `ready`、`degraded_optional`、`sidecar_ready` |
| `required` | 是不是核心必需服務 |
| `cost_class` | 本地、免費雲端、付費雲端 |
| `task_types` | 適合處理什麼任務 |
| `fallback` | 失敗時回退到誰 |
| `owner_agent` | 哪個智能體主要負責 |

目前登記的能力包含：

| 能力 | 定位 |
|---|---|
| `perob` | 主系統、大門、總管 |
| `desktop_bridge` | 本地回退橋 |
| `openclaw` | 工具任務控制平面 |
| `lobster` | 確定性工作流與 approval checkpoint |
| `airllm` | 本地模型側車 |
| `ollama` | 本地模型服務 |
| `faiss` | 向量索引 |
| `sqlite_memory` | 長期記憶資料庫 |
| `git` | 版本真相與任務脈絡 |
| `n8n` | optional 排程 |
| `cloud_providers` | 雲端模型供應商 |

### 2.2 流量總管：`core/traffic_governor.py`

流量總管就像公司的電話費管家。它不直接打電話，而是先決定：

1. 這是聊天、研究、修程式、安全、影片，還是伺服器問題？
2. 本地記憶是否已經有高信心答案？
3. 要不要叫 OpenClaw？
4. 要不要用雲端？
5. 可不可以先用本地模型或免費 provider？

核心規則：

- 本地記憶高信心命中：不呼叫雲端。
- 一般討論：不走 OpenClaw。
- 修 bug、Debug、Git、伺服器、工作流：優先考慮 OpenClaw，再回退 DesktopBridge。
- n8n 永遠不是核心必需。
- fallback 是保險，不是成功本身。

---

## 3. 已接入的公開資料出口

### 3.1 `/health/ready`

現在 readiness 裡會包含：

- `memory_autosave`
- `aeg_training`
- `openclaw`
- `optional_services.n8n`
- `capability_registry`

這代表健康檢查不只看「有沒有開」，也能看到「有哪些能力已報到」。

### 3.2 `/api/runtime/topology`

現在拓樸圖會包含：

- `services`
- `routing`
- `readiness`
- `capability_registry`
- `traffic_governor`

這是給前端、診斷工具、其他智能體看的系統地圖。

### 3.3 `/api/frontend/snapshot`

前端快照現在也帶出：

- `capability_registry`
- `traffic_governor`

這讓前端未來可以顯示「目前系統為什麼選本地、為什麼不走 OpenClaw、為什麼 n8n 離線但不影響對話」。

---

## 4. 重要路由改變

### 4.1 一般 auto 對話改成本地優先

修改前：

> 如果 `.env` 裡 `CHAT_PREFERRED_PROVIDER=groq`，一般討論可能直接走 Groq。

修改後：

> `auto` 模式的一般討論先走 `open_source`。只有使用者明確選 Groq/OpenAI/Gemini/NVIDIA 時，才尊重指定雲端 provider。

日常比喻：

> 如果只是平常聊天，先找公司內部同事。除非你明確說「我要請外部顧問」，才去花雲端流量。

### 4.2 OpenClaw 只接工具型任務

OpenClaw 現在不應該搶一般聊天。

會考慮 OpenClaw 的任務：

- 修 bug
- Debug
- Git
- server / 伺服器
- workflow
- 啟動 / 重啟
- 安全沙盒類任務

不該走 OpenClaw 的任務：

- 一般聊天
- 問候
- 低風險說明
- 可以由本地記憶直接回答的內容

### 4.3 OpenClaw 狀態新增可讀回覆判斷

OpenClaw adapter 現在記錄：

- `last_forward_at`
- `last_forward_error`
- `last_readable_response`

這是為了避免「OpenClaw 有連線」被誤判成「OpenClaw 完成任務」。

---

## 5. 雙系統兼容方向

目前建議維持：

| 系統 | 角色 |
|---|---|
| Mac | 主伺服器、Perob、Git 主工作區、資料中樞 |
| Windows | 使用端、副工作站、未來 worker |

雙系統規則：

- Git 遠端是版本真相。
- API 格式不能因 Mac/Windows 改變。
- 路徑必須走抽象，不把 `/Volumes/...` 或 `G:\...` 寫死進 manifest。
- Windows 先連 Mac 的服務，之後再接成 worker。
- AirLLM 這種重型模型環境要獨立，不污染主 runtime。

---

## 6. 已驗證測試

本次新增並通過：

```bash
python3 -m unittest tests.test_super_platform_contract
```

通過重點：

- AirLLM 被視為 isolated sidecar。
- n8n 是 optional，且 `degrades_core_chat=false`。
- 本地記憶高信心命中時不允許雲端。
- 一般討論不走 OpenClaw。
- 工具任務路由順序為 OpenClaw -> DesktopBridge。
- WebServer readiness/topology 會輸出 capability registry 與 traffic governor。
- auto 討論即使 env 偏好 Groq，也先選 `open_source`。

也通過：

```bash
python3 -m unittest tests.test_super_platform_contract tests.test_perob_mainline_health_contract tests.test_openclaw_forwarding_contract
python3 -m py_compile core/capability_registry.py core/traffic_governor.py core/openclaw_adapter.py core/web_server.py desktop_chat_app.py
```

---

## 7. 後續要做但本次不硬塞的事項

### P1：讓前端顯示路由理由

例如：

- 本次使用本地記憶回答。
- 本次沒有走 OpenClaw，因為是一般討論。
- 本次走 OpenClaw，因為偵測到 Debug 任務。
- n8n 目前離線，但不影響核心對話。

### P1：OpenClaw 真任務完成率驗證

下一步要測：

- OpenClaw 有沒有真的回可讀內容。
- OpenClaw 只回 challenge/event 時是否正確回退。
- 回退後是否寫入審計。

### P2：AirLLM 背景 worker

目前完成的是側車狀態登記，不是把 AirLLM 推理接到對話。下一步應該做：

- `airllm_worker` 啟動器。
- 背景 job queue。
- 模型下載前的磁碟與記憶體檢查。
- 推理結果回傳主系統。

### P2：AEG/RAG 信心分層

下一步要讓 RAG 回傳：

- 高信心直接回答。
- 中信心附來源。
- 低信心問下一個缺口。
- 弱關聯不能硬回答。

---

## 8. 這次的劇本修正

原本劇本：

> 使用者問問題，系統憑感覺叫角色，OpenClaw 在線就好像算可用，雲端 provider 可能被偏好牽走。

新的劇本：

> 使用者問問題，總管先分類；圖書館先查；流量總管決定省錢路線；工具任務才叫 OpenClaw；OpenClaw 沒有可讀成果就回退；n8n 不影響核心；AirLLM 留在側車實驗室。

這比較接近你要的主目標：

> 不是讓系統壞了也勉強維持，而是讓系統一開始就知道誰該做什麼、為什麼這樣做、失敗時怎麼有紀錄地補救。

---

## 9. 2026-06-08 實作後驗證補記

### 9.1 背景啟動短命問題已修正

原本 `tools/manage_perob_stack.sh` 在外接硬碟工作區使用 `nohup &` 啟動服務時，啟動腳本會短暫看到 `5001` 與 `5443` 成功，但命令結束後背景程序也被帶走，造成 PID 檔仍在、實際服務已消失。

修正方式：

- 新增 `tools/launch_detached.py`。
- 使用 `start_new_session=True` 啟動 Perob 後端與 HTTPS proxy。
- PID 寫入 `logs/pids/`。
- stdout/stderr 保持寫入 `logs/launchagents/`。

驗證結果：

- `5001` 後端程序 PPID 已變成 `1`，代表不再依附啟動命令。
- `5443` proxy 程序 PPID 已變成 `1`。
- 重啟後等待 5 秒仍持續監聽。

生活化說法：

> 以前像是店員被綁在開店車上，車一走店也關了。現在店員正式留在店裡，不會因為啟動命令結束就下班。

### 9.2 Web Server 客戶端斷線安全處理

原本 `/api/frontend/snapshot` 或其他 JSON 回應在客戶端中途斷線時，`self.wfile.write()` 可能丟出 `BrokenPipeError`，造成後端 console 出現大段錯誤堆疊。

修正方式：

- `core/web_server.py` 新增 `_is_client_disconnect()`。
- `_send_json()`、`_send_text()`、`_send_redirect()` 對 `BrokenPipeError`、`ConnectionResetError`、`EPIPE`、`ECONNRESET` 採可恢復處理。
- 非客戶端斷線的錯誤仍會重新丟出，不會掩蓋真正 bug。

生活化說法：

> 客人點餐後突然離開，廚房不能因此整間停擺；但如果是瓦斯爐壞掉，仍然要報錯。

### 9.3 自動討論最低流量路由已接入 send_message

原本 `model=auto` 的一般討論雖然會先選 `open_source`，但如果本地 Ollama 不健康，會自動 fallback 到 NVIDIA 或 Groq，導致普通聊天也消耗雲端 API。

修正方式：

- 新增 `_allow_cloud_fallback_for_requested_backend()`。
- 新增 `_should_attempt_live_llm_backend()`。
- `model=auto + discussion` 不因本地模型不健康而自動花雲端。
- 若本地模型不健康，快速改用本地規則/記憶回覆，並標記 `open_source_unhealthy_local_first`。
- 若使用者明確選擇 `groq`、`nvidia`、`openai`、`gemini`，仍尊重指定。

實測結果：

```json
{
  "ok": true,
  "backend": "open_source",
  "duration_s": 2.354,
  "llm_live": {
    "attempted": false,
    "fallback_used": true,
    "provider": "open_source",
    "fallback_reason": "open_source_unhealthy_local_first"
  }
}
```

生活化說法：

> 自動模式像總機省錢規則：一般聊天先用內部資料與本地員工；本地員工沒打卡時，不要立刻打昂貴國際電話，而是先用公司內部 SOP 回覆。只有你明確指定外部專家，才打外線。

### 9.4 入口驗證結果

本次驗證順序固定為：

1. `http://127.0.0.1:5001/status`
2. `https://perob.com:5443/status`
3. `http://127.0.0.1:5001/api/runtime/topology`
4. `http://127.0.0.1:5001/api/frontend/snapshot`
5. `POST /api/send_message`

結果：

| 項目 | 結果 | 備註 |
|---|---|---|
| `5001 /status` | 通過 | 約 0.01 秒 |
| `5443 /status` | 通過 | HTTPS proxy 可用，偶爾較慢 |
| `/api/runtime/topology` | 通過 | 回傳 capability registry 與 traffic governor |
| `/api/frontend/snapshot` | 通過 | 約 1.5 秒，約 32KB |
| `/api/send_message` | 通過 | auto discussion 不再自動打雲端 |
| 前端 HTML | 通過 | `chat_shell` 回傳 200，標題與 API 腳本存在 |

### 9.5 測試結果

```bash
python3 -m unittest \
  tests.test_super_platform_contract \
  tests.test_perob_mainline_health_contract \
  tests.test_openclaw_forwarding_contract \
  tests.test_desktop_web_compat_routes \
  tests.test_route_prefix_candidates_contract
```

結果：

```text
Ran 27 tests
OK
```

靜態檢查：

```bash
python3 -m py_compile \
  tools/launch_detached.py \
  core/capability_registry.py \
  core/traffic_governor.py \
  core/openclaw_adapter.py \
  core/web_server.py \
  desktop_chat_app.py
```

結果：通過。

### 9.6 仍需中期處理

- 目前 runtime 仍是 Python 3.14，會出現 SWIG/Pydantic v1 類 warning；主 runtime 仍應固定到 Python 3.11 或 3.12。
- `5443` HTTPS proxy 可用，但偶爾比 `5001` 慢，後續可加 proxy latency 指標。
- Playwright 未安裝，因此這次只完成 HTML/API 層驗證，尚未完成點擊級瀏覽器自動化。
- AirLLM 目前仍是側車登記與安裝基礎，尚未接成正式背景 worker。

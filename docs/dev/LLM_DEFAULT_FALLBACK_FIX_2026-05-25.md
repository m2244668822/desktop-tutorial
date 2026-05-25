# 對話預設真 LLM + 模板降級修復報告（2026-05-25）

## 修復時間點（Asia/Taipei）
- 2026-05-25 20:13:11：完成 `desktop_chat_app.py` 主修復
- 2026-05-25 20:13:34：完成 `core/web_server.py` 供應商狀態修復
- 2026-05-25 20:15 後：重啟 5001 並完成端到端驗證

## 低級錯誤根因（為什麼你會覺得「很死板」）
1. 對話路徑沒有真的呼叫 LLM
   - 程式把 `backend=nvidia/openai` 當成狀態標籤回傳，但一般聊天實際上多數走 `_build_conversational_reply()` 的模板字串。
2. 前端供應商狀態有硬編碼
   - `/api/frontend/snapshot` 曾固定回傳 key 已配置，造成觀測與實際執行脫節。

> 結論：系統「看起來像在用雲端」，但回覆實際常由本地模板函式輸出，這就是回覆單一與鬼打牆的主因。

## 本次修復內容

### A. 對話預設走真 LLM（只在失敗時 fallback）
- 新增 OpenAI-compatible 真實呼叫（NVIDIA / OpenAI / Groq / Gemini）
- 新增 Ollama 呼叫（open_source）
- 新增 live metadata：每輪回傳 `llm_live`（是否真的打 API、端點、模型、是否 fallback）

關鍵檔案：
- `desktop_chat_app.py`
  - `DEFAULT_CHAT_MODEL_BY_PROVIDER`
  - `_provider_runtime_config()`
  - `_call_openai_compatible_chat()`
  - `_call_ollama_chat()`
  - `_generate_live_llm_reply()`
  - `send_message()`：先走 live LLM，再模板 fallback

### B. 模板降級（fallback）邏輯保留
- 當 API timeout / 401 / 空回應 / provider 設定不完整時，才落回既有模板函式。
- 系統不中斷，仍可回覆。

### C. 供應商狀態改為動態
- `core/web_server.py` 的 `/api/frontend/snapshot` 改為讀取 `bridge.get_api_onboarding_info()`，不再硬寫 True。
- `desktop_chat_app.py` 的 `get_api_onboarding_info()` 改用 `cns_frontend_provider_status()`。

## 驗證結果

### 1) 真 LLM 已實際被呼叫
- `POST /chat/agent` 回傳：
  - `llm_live.ok = true`
  - `llm_live.transport = openai_compatible`
  - `llm_live.endpoint = https://integrate.api.nvidia.com/v1/chat/completions`
  - `llm_live.model = meta/llama-3.1-8b-instruct`
  - `llm_live.fallback_used = false`

### 2) 服務檢查
- `http://127.0.0.1:5001/status`：ok
- E2E：`tests/tools/check_chat_shell_e2e.py` 全部 PASS

## 為什麼這樣改
- 你的目標是「智能體回覆要有真實推理與多樣性」，這必須以真 LLM 為預設。
- 模板只能當保險絲，不能當主引擎。
- 同時補上動態 provider 狀態，讓觀測面與執行面一致，避免再被假訊號誤導。

## 後續建議
1. 把 `CHAT_PREFERRED_PROVIDER` 明確設成你要的主供應商（例如 `nvidia`）。
2. 若要更像對話助手，可把 `CHAT_LLM_TEMPERATURE` 調到 `0.55~0.7`。
3. 保留 fallback，但在前端顯示「本輪為模板降級」提示，方便立即察覺。

## Related Docs

- [Cross-System Linkage and Consolidation (2026-05-26)](./CROSS_SYSTEM_LINKAGE_AND_DOC_CONSOLIDATION_2026-05-26.md)
- [Agent Reply Optimization Verification](./AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md)
- [Mac / Windows Shared Workspace Runbook](./MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md)

## Task Status Snapshot (2026-05-26)
- Status: `completed-core`
- Completed:
  - Default path documented as live LLM first; template only fallback.
  - Provider snapshot changed from hardcoded to dynamic data source.
- Pending:
  - Keep fallback observability in UI to detect degraded rounds quickly.


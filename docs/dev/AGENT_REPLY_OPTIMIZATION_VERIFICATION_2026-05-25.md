# 智能體回覆優化與系統驗證報告（2026-05-25）

## 驗證目標
1. 開啟主前後端服務（5001）
2. 確認 n8n 獨立常駐（5678）
3. 實測「重複回覆/鬼打牆」是否改善
4. 再確認上次 training overlay 是否已合併到目前主線

## 服務狀態（最終實測）
- `5001`：UP（主入口）
- `5678`：UP（n8n）
- `5679`：UP（n8n task broker）
- `11434`：UP（Ollama）

## 本輪修正（已落地）
### A. 智能體回覆優化（desktop_chat_app.py）
- 一般非系統問題改為「直接內容回答」，不再只回模板話術。
- 反重複（loop breaker）在重問時，會輸出不同內容組合，不再只換前綴。
- 新增主題焦點清理與數量解析，避免主題被切成破碎短詞。

關鍵函式：
- `_build_loop_breaker_reply`
- `_build_conversational_reply`
- `_focus_topic`
- `_extract_requested_count`
- `_build_general_non_system_reply`

### B. 前端契約與相容（core/web_server.py）
- `inject_web_bridge_shim` 修正為「缺 shim 才注入」，避免 chat_shell 缺 bridge。
- `/api/get_status` 新增 `monitoring` 欄位別名（保留既有 `monitor`）。
- 修復多處編碼損壞導致的路由映射字串斷裂與註解吞程式碼問題。

## 回覆優化實測（API）
測試路徑：`POST /chat/agent`

- 第 1 次：
  - 問題：`我今天心情很亂，請給我三個放鬆方法。`
  - 結果：給出 3 條可執行步驟。

- 第 2 次（同題重問）：
  - 結果：觸發防重複，改輸出「另一組步驟組合」並標記已避開近似回覆。

## 路由與前端 E2E（最終）
`tests/tools/check_chat_shell_e2e.py --base-url http://127.0.0.1:5001`
- 結果：**全部 PASS**
  - `/health` PASS
  - `/chat_shell` PASS
  - `pywebview bridge` PASS
  - `/api/get_status` monitoring payload PASS

## 上次訓練（training overlay）合併狀態（2026-05-28 更新）
- 目前工作分支：`codex/training-overlay-20260525`
- 上次訓練提交：`2f7f1e5`
- 判定：**已合併且在主線可用**

佐證：
- `docs/dev/TRAINING_FUSION_SCORE_ANALYSIS_2026-05-25.md`：存在
- `data/agent_penalty_events.jsonl`：存在
- `git merge-base --is-ancestor 2f7f1e5 HEAD`：回傳 `0`（祖先關係成立）

## 結論
- 前後端已成功開啟，且主入口與 n8n 均可用。
- 智能體「重複回覆」已從模板回覆改善為內容型回覆，重問時會變換輸出。
- 上次 training overlay 已併入目前分支；下一步轉為「文件治理與回歸驗證常態化」。

## Related Docs

- [Cross-System Linkage and Consolidation (2026-05-26)](./CROSS_SYSTEM_LINKAGE_AND_DOC_CONSOLIDATION_2026-05-26.md)
- [LLM Default Fallback Fix](./LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md)
- [Single Entry Gateway Policy](./SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md)

## Task Status Snapshot (2026-05-28)
- Status: `merged-and-followup`
- Completed:
  - Loop-breaker and route compatibility checks passed in prior verification.
  - Training overlay branch artifacts merged into current working branch.
- Pending:
  - Continue document governance consolidation in `docs/dev/MD_BUNDLE_INDEX_2026-05-27.md`.

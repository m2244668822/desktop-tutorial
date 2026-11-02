# n8n 訓練／評估流水線設計

日期：2026-11-02  
狀態：待使用者確認

## 意圖

把 n8n 從「服務有啟動」提升成可手動驗證的訓練／評估入口：先確認 Trevor 核心健康，再執行 retrieval golden-set 評估，最後產生隱私安全的訓練準備報告。這一版不開自動排程，也不把 n8n 變成語言理解核心。

## 已知現況

- n8n 2.37.10 的 `5678` 編輯器與 `5679` task broker 正常監聽。
- n8n `/healthz` 回應 200，但本機 SQLite 的 `workflow_entity` 目前是 0。
- 專案已有手動觸發的 `automation/n8n/trevor-local-health-check.json`，但先前 Windows／Node 24 的 CLI 匯入未穩定完成。
- Trevor 已有可重複執行的 retrieval evaluator 與 `training_status_latest.json` 產生器。

## 目標

1. 建立一份可匯入、可手動執行、可回滾的 n8n 訓練／評估工作流。
2. 將三個階段串起來：健康檢查 → retrieval 評估 → training status 報告。
3. 只輸出狀態、指標、來源路徑與 gate 結果，不把私密記憶內容送進 n8n。
4. 讓失敗可定位：每一階段都要有明確的中文摘要、錯誤原因與下一步。
5. 保持 n8n optional；即使 n8n 關閉，5001 核心聊天與 Trevor 記憶路徑仍可運作。

## 非目標／反目標

- 本輪不啟用 Schedule Trigger、不做背景自動訓練。
- 本輪不做模型權重微調；只執行 retrieval 評估與本地 adaptive policy／狀態報告。
- 本輪不新增外部 webhook、雲端憑證或第三方 API。
- 不用直接修改 n8n SQLite 來「偽造匯入成功」。

## 候選方案

### A：只匯入最小 health workflow

風險最低，但無法直接驗證 retrieval 與訓練狀態，對目前的訓練目標不足。

### B：手動訓練／評估流水線（選定）

以 Manual Trigger 開始，依序執行：

1. HTTP Request 讀取 `http://127.0.0.1:5001/health/ready`。
2. Gate 檢查 `required_ready=true`；失敗時停止後續步驟並輸出中文原因。
3. 本機受限命令執行 retrieval evaluator，寫入既有 `retrieval_eval_latest.json`。
4. 本機受限命令產生 `training_status_latest.json`。
5. 統一輸出 `gate_passed`、指標、報告路徑、中文 `intro_zh`／`summary_zh`／`field_descriptions_zh`。

優點是直接覆蓋訓練品質；代價是需要處理 Windows 本機命令、逾時與匯入驗證。所有命令都固定在工作區與既有 Python 環境內執行。

### C：直接排程與告警

長期自動化價值最高，但在工作流尚未匯入、手動執行尚未穩定前，會把錯誤變成重複噪音；本輪不選。

## 工作流契約

每次執行都應產生以下結構：

```json
{
  "schema_version": 1,
  "gate_passed": true,
  "intro_zh": "中文說明：...",
  "summary_zh": "...",
  "health": {"required_ready": true, "optional_gaps": []},
  "retrieval": {"cases": 0, "hit_rate": 0.0, "mrr": 0.0, "stale_retrieved": 0},
  "training": {"readiness": {"data": true, "retrieval": true, "backup": true, "git": true}},
  "artifacts": {"retrieval_report": "...", "training_report": "..."},
  "errors": []
}
```

輸出禁止包含 retrieved memory text、API key、cookie、加密內容或完整對話內容；只保留 metadata 與 aggregate metrics。

## 驗收條件

- n8n workflow 可被匯入且資料庫中出現 1 個 inactive workflow。
- 手動執行能完成三階段，或在正確階段以可讀錯誤停止。
- 健康檢查、retrieval evaluator、training status 三者的輸出可互相對應。
- `hit_rate`、`mrr`、citation correctness、stale／privacy 指標不被改寫或遺失。
- n8n 停止時，5001 `/health/ready` 與 `/chat_shell` 仍可用。
- 產生測試與匯入 smoke test；不要求開啟排程。

## 回滾

回滾只需停用或刪除這一份 n8n workflow，並保留 Trevor 既有報告檔；不得回寫或刪除 n8n 其他工作流與資料庫。

## 尚待確認

這份設計等待使用者確認後，才進入 implementation plan 與程式／工作流修改。

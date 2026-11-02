# Trevor n8n 工作流

## 最小健康檢查

`trevor-local-health-check.json` 是預設停用、只能手動觸發的本機工作流：

1. 手動啟動。
2. 只讀取 `http://127.0.0.1:5001/health/ready`。
3. 不使用憑證、不寫入 Trevor、不連外網。

匯入：

```powershell
.\tools\start_n8n_windows.ps1 import:workflow --input=.\automation\n8n\trevor-local-health-check.json
```

匯入後先在 n8n 編輯器手動執行一次。確認回傳 `status=ready` 後，若確實需要排程，再另外建立 Schedule Trigger；不要直接把這份基準工作流改成自動執行。

## 手動訓練／檢索評估

`trevor-training-evaluation.json` 是獨立的手動訓練／評估工作流，不會覆寫上面的 health 基準工作流，也不會自行排程。它依序：

1. 讀取 `http://127.0.0.1:5001/health/ready`。
2. 健康 gate 通過後，呼叫 localhost-only 的 `POST /api/n8n/training-evaluation` bridge；bridge 再呼叫固定工作區 wrapper `tools/n8n_training_evaluation.py`。
3. 執行 retrieval golden-set 評估與 training status 報告產生器。
4. 只輸出 `run_id`、gate、aggregate metrics、報告路徑與中文摘要。

這條 bridge 是刻意的權限邊界：n8n 不開啟全域 Execute Command，也不接收任意命令或動態 URL；只有本機 `127.0.0.1` 可以觸發，訓練 wrapper 的輸出仍維持 aggregate-only。

匯入前可先做離線契約檢查：

```powershell
& .venv/Scripts/python.exe tools/validate_n8n_training_workflow.py --workflow automation/n8n/trevor-training-evaluation.json
```

執行時請保持 `active=false`，先手動 Run 一次；若 gate 未通過，保留 `gate_passed=false` 的輸出，不要把它改成成功。回滾只需停用或刪除這份 training workflow，保留原本 health workflow。

本機匯入 smoke test 會先確認 n8n `/healthz`，再以 30 秒上限執行 import；`N8N_USER_MANAGEMENT_DISABLED=true` 只傳給匯入子程序，不會修改常駐 n8n 的認證設定：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_test_n8n_training_evaluation.ps1
```

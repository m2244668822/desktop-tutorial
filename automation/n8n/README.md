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

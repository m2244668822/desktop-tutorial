---
name: workspace-butler
description: 工作區整理與自動化管理工具。用於將雜亂的報告、歷史檔案、備份檔與快取目錄分類歸檔，保持專案主目錄清爽。
---

# Workspace Butler

您的專案管家，負責保持開發環境的整潔。

## Stability and Conflict Policy

1. 不直接刪除執行主線檔案（`system_main.py`, `desktop_chat_app.py`, `core/`, `tools/agent_autonomy_daemon.py`）。
2. 若偵測到其他技能也可處理同一任務，優先回傳「整理建議」而非直接移動檔案。
3. 與自治守護模式協作時，只處理 `reports/`、`archive/`、暫存資料夾，不改動任務佇列與權限設定檔。

## 核心功能

1. **報告歸類**：自動偵測並移動所有報告檔案（包含 REPORT, STATUS, SUMMARY 字樣）至 `reports/`。
2. **歷史歸檔**：將帶有日期（如 2026-03-07）的舊檔案移入 `archive/`。
3. **快取清理**：刪除 `__pycache__`、`.ruff_cache` 等暫存資料夾，節省空間。
4. **備份收納**：集中管理 `.bak` 與 `.backup` 檔案至 `archive/backups/`。

## 如何使用

### 執行完整清理

執行腳本進行自動化整理：

```bash
python3 scripts/organize_workspace.py
```

## 資源

- **scripts/organize_workspace.py**: 工作區整理核心邏輯
- **tools/agent_autonomy_daemon.py**: 自治守護狀態來源（避免清理該路徑）

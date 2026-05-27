# PostgreSQL 遷移驗證報告（正式樣板）

- 日期：2026-05-14
- 專案：m2244668822/desktop-tutorial
- 驗證方式：GitHub Actions `verify-showcase`
- 資料來源：`tmp/fixture.db`（固定測試資料）
- 目標資料庫：CI PostgreSQL Service (postgres:16)

## 固定驗證項

1. 核心表存在性（PostgreSQL）
2. 核心表筆數一致（SQLite vs PostgreSQL）
3. 抽樣資料雜湊一致
4. Repo 安全策略（Private / Collaborators / Actions）

## 驗證結果

- 本檔為基準樣板，正式結果以 workflow artifact 為準：
  - `logs/verification_reports/latest_verification_report.json`
- 建議每次 main 發布前下載 artifact 並歸檔到 `docs/dev/reports/`。

## 驗收門檻

- `errors = 0`
- `warnings = 0`（或需明確註記豁免理由）
- row count mismatch = 0
- sample hash mismatch = 0

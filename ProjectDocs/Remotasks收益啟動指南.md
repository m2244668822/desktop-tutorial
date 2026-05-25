# Remotasks 收益啟動指南

## 你需要先知道

- 不需要提供你的加密貨幣收發連結給我。
- 先以 Remotasks 平台內建收款流程為主（平台綁定支付方式）。
- 除非你要做鏈上對帳自動化，否則不必先提供錢包地址。

## 今日可執行 MVP

1. 完成 Remotasks 帳號與身份驗證。
2. 選 1~2 種高需求任務類型（例如：影像標註、內容審核）。
3. 每天固定兩個工作時段（例如 09:00-11:00、20:00-22:00）。
4. 每完成一批任務，立刻記錄時數與收入。

## 本地收益追蹤工具

已提供檔案：

- `tools/remotasks_revenue_tracker.py`
- `data/remotasks/revenue_log.json`

### 新增一筆記錄

```bash
python3 tools/remotasks_revenue_tracker.py add \
  --task-id RT-20260301-001 \
  --category image_annotation \
  --hours 2.5 \
  --amount-usd 18.75 \
  --status pending \
  --note "首日測試"
```

### 看最近記錄

```bash
python3 tools/remotasks_revenue_tracker.py list --limit 10
```

### 看收益摘要

```bash
python3 tools/remotasks_revenue_tracker.py summary
```

## 建議 KPI（第一個 30 天）

- 日工時：2~4 小時
- 週工作天：5~6 天
- 首月目標：先穩定流程與品質，再拉高單日完成量
- 追蹤指標：
  - 每小時收益（USD/h）
  - 已付 vs 待付金額
  - 任務退回率

## 風險與安全

- 不要把私鑰、助記詞、交易所登入資訊放進專案或訊息。
- 平台收款與帳務資料分離管理。
- 所有收入資料先用本地 JSON 留存，再每週匯出備份。

## 下一步（可選）

- 加入每週自動匯總（CSV / Markdown 報表）。
- 連到你現有的 `task_and_revenue_manager.py` 做統一收入面板。

# Remotasks 自動週報使用說明

## 快速開始

### 生成每日報告

```bash
python3 tools/remotasks_report_generator.py --type daily
```

輸出位置：`reports/remotasks_YYYYMMDD_daily.md`

### 生成每週報告

```bash
python3 tools/remotasks_report_generator.py --type weekly
```

輸出位置：`reports/remotasks_YYYYMMDD_weekly.md`

### 導出 CSV（用於 Excel 分析）

```bash
# 導出過去 30 天資料（預設）
python3 tools/remotasks_report_generator.py --type csv

# 導出過去 90 天資料
python3 tools/remotasks_report_generator.py --type csv --days 90
```

輸出位置：`reports/remotasks_YYYYMMDD_export.csv`

---

## 進階用法

### 自訂輸出路徑

```bash
python3 tools/remotasks_report_generator.py \
  --type daily \
  --output "我的報告/今日工作摘要.md"
```

### 指定資料來源

```bash
python3 tools/remotasks_report_generator.py \
  --type weekly \
  --data "備份/revenue_log_2026.json"
```

---

## 每日自動化（cron 定時任務）

### Mac / Linux 設置

1. 編輯 crontab：

```bash
crontab -e
```

2. 添加每日任務（每天 23:50 自動生成）：

```bash
# 每日報告
50 23 * * * cd /Volumes/智能體/城城城程式 && python3 tools/remotasks_report_generator.py --type daily >> logs/report_generator.log 2>&1

# 每週報告（每週日 23:55）
55 23 * * 0 cd /Volumes/智能體/城城城程式 && python3 tools/remotasks_report_generator.py --type weekly >> logs/report_generator.log 2>&1
```

### 驗證 cron 任務

```bash
# 查看已設定的任務
crontab -l

# 手動測試生成
python3 tools/remotasks_report_generator.py --type daily
```

---

## 報告內容說明

### 每日報告包含

- **今日摘要**
  - 完成任務數
  - 總工時
  - 總收益
  - 平均時薪

- **按類別統計**
  - 各任務類型的工時與收益
  - 每類的平均時薪

- **詳細記錄**
  - 每筆任務的完整資訊
  - 付款狀態標記（✅ 已付 / ⏳ 待付）

### 每週報告包含

- **週度摘要**
  - 全週統計（含已付/待付金額）
  - 日均工時與日均收益

- **按類別統計**
  - 各類別的收益佔比
  - 排序由高到低

- **每日趨勢**
  - 過去 7 天的逐日數據
  - 方便觀察工作模式

### CSV 導出用途

- Excel / Google Sheets 樞紐分析
- 數據可視化（圖表）
- 跨月份對比
- 稅務申報準備

---

## 整合到現有系統

### 與任務管理器整合

編輯 `business/task_and_revenue_manager.py`，在完成任務時自動更新：

```python
from tools.remotasks_revenue_tracker import RemotasksRevenueTracker

tracker = RemotasksRevenueTracker()

# 完成任務後記錄
tracker.add_entry(
    task_id=task_info['id'],
    category=task_info['type'],
    hours=task_info['actual_hours'],
    amount_usd=task_info['payment_usd'],
    status='pending',
    note=f"自動記錄 via task_manager"
)
```

### 每日工作流程

1. **早上 9:00** - 查看昨日報告

```bash
cat reports/remotasks_*_daily.md | tail -50
```

2. **工作時間** - 完成 Remotasks 任務

3. **完成任務後** - 立即記錄

```bash
python3 tools/remotasks_revenue_tracker.py add \
  --task-id RT-$(date +%Y%m%d)-001 \
  --category YOUR_CATEGORY \
  --hours 2.0 \
  --amount-usd 15.00 \
  --status pending
```

4. **晚上 23:50** - 自動生成報告（cron 執行）

5. **每週日晚上** - 查看週報，規劃下週目標

---

## 故障排除

### 問題：報告顯示「無記錄」

**原因**：可能使用了空的或錯誤的資料檔

**解決**：

```bash
# 檢查資料檔內容
cat data/remotasks/revenue_log.json

# 確認有記錄
python3 tools/remotasks_revenue_tracker.py list
```

### 問題：cron 任務沒執行

**檢查方法**：

```bash
# 1. 確認 cron 服務運行中
# Mac: 檢查系統偏好設定 > 安全性與隱私 > 完全磁碟存取權限

# 2. 檢查日誌
cat logs/report_generator.log

# 3. 手動測試完整路徑
/usr/local/bin/python3 /Volumes/智能體/城城城程式/tools/remotasks_report_generator.py --type daily
```

### 問題：CSV 在 Excel 中文亂碼

**原因**：編碼問題

**解決**：已使用 `utf-8-sig` 編碼（支援 Excel），如仍有問題：

- 用 Excel「資料 > 從文字/CSV」導入
- 選擇 UTF-8 編碼

---

## 未來擴展建議

1. **自動備份到雲端**
   - 每週自動上傳到 Google Drive / Dropbox
2. **Slack / Discord 通知**
   - 每日報告自動發送到頻道

3. **圖表可視化**
   - 生成收益趨勢圖（PNG）
   - 使用 matplotlib 或 plotly

4. **多平台整合**
   - 支援 Appen、Lionbridge 等其他平台
   - 統一收益儀表板

---

**需要幫助？** 參考主要文檔：[Remotasks收益啟動指南.md](Remotasks收益啟動指南.md)

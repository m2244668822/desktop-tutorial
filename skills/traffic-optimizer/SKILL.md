---
name: traffic-optimizer
description: API 流量監控與成本優化工具。用於分析消耗趨勢、設定預算警報，並在消耗過高時自動建議切換到經濟型模型（如 gemini-1.5-flash）。
---

# Traffic Optimizer

本技能旨在幫助用戶管理 API 流量消耗，避免產生預期外的成本，並在高性能與低成本之間取得平衡。

## Stability and Conflict Policy

1. 本技能只提供流量建議，不直接覆寫 API key 與權限檔案。
2. 若與任務自治守護同時運作，避免修改 `task_queue.json`，僅輸出建議給總管路由決策。
3. 遇到未配置 token 或權限不足時，回報 `permission snapshot`，不進行自動重試風暴。

## 核心功能

1. **流量監控**：即時查看今日與累計消耗。
2. **預算警報**：當消耗超過自定義閾值時發出提醒。
3. **模型切換建議**：偵測到高流量使用時，建議切換至更經濟的模型。
4. **自動日誌整理**：定期歸檔舊的消耗數據。

## 如何使用

### 監控當前流量

執行 `scripts/monitor_usage.py` 來獲取即時報告：

- 消耗 < 0.05：安全
- 消耗 > 0.05：警報 (Warning)
- 消耗 > 0.08：建議切換模型 (Switch Suggested)

### 模型切換策略

當今日任務量巨大時，優先考慮使用以下指令：

```bash
# 切換至更便宜的模型
gemini config set model gemini-1.5-flash
```

## 資源

- **scripts/monitor_usage.py**: 流量監控核心邏輯
- **references/budget_policy.md**: 預算策略定義
- **data_hdd_storage/autonomy/daemon_state.json**: 權限與運行快照

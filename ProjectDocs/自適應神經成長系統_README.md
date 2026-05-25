# 🌱 自適應神經成長系統

> **讓智能體在使用中自然成長，而非一次性升級**

## 🎯 一句話說明

根據累積的對話數據，系統會**自動調整**神經網絡規模和連接強度，實現真正的「做中學」。

## ⚡ 快速開始

```bash
# 1. 正常使用聊天系統（自動啟用成長）
./start_groq_memory_chat.py

# 2. 查看成長歷程
./view_neural_growth.sh

# 3. 每週維護一次（或每 100 個新對話）
./maintain_neural_system.sh
```

## 📊 成長階段

```
  初生期 (0+)     → 神經元 ×1.0  |  基礎架構
    ↓
  學習期 (500+)   → 神經元 ×1.2  |  開始擴展
    ↓
  成長期 (1000+)  → 神經元 ×1.4  |  快速成長
    ↓
  發展期 (1500+)  → 神經元 ×1.6  |  持續優化
    ↓
  成熟期 (2000+)  → 神經元 ×1.8  |  穩定階段
    ↓
  進化期 (3000+)  → 神經元 ×2.0  |  進階能力
```

## 🔗 核心機制

### 1. 自適應規模調整

- 根據對話數量自動判斷階段
- 平滑過渡到下一階段（提前 20% 開始）
- 根據使用頻率微調 (±20%)

### 2. 漸進式連接強化

- 追蹤神經連接的使用頻率
- 頻繁使用 → 逐步增強（對數增長）
- 很少使用 → 輕微衰減
- 保持系統靈活性

### 3. 成長記錄

- `logs/neural_growth_log.json` - 成長事件時間軸
- `logs/connection_usage.json` - 連接使用統計

## 📈 效果展示

### 神經元增長曲線

```
100 對話   ████████        神經元: 36  (初生期)
500 對話   ██████████      神經元: 43  (學習期)
1000 對話  ████████████    神經元: 50  (成長期)
2000 對話  ██████████████  神經元: 65  (成熟期)
3000 對話  ████████████████神經元: 72  (進化期)
```

### 連接強化示例

```
Input → Semantic 連接:
  初始:     0.50
  100 次:   0.52  (+4%)
  500 次:   0.58  (+16%)
  1000 次:  0.65  (+30%)
```

## 🛠️ 維護命令

```bash
# 查看成長狀態（完整）
./view_neural_growth.sh

# 執行連接強化
./maintain_neural_system.sh

# 僅查看摘要
./maintain_neural_system.sh --status
```

## 📚 文件結構

```
500/llama32-chat/learning/
├── adaptive_neural_growth.py              # 自適應成長管理
├── progressive_connection_strengthening.py # 連接強化系統
└── neural_hub.py                          # 神經中樞（已整合）

tools/
├── view_neural_growth.py                  # 成長查看工具
└── progressive_neural_maintenance.py      # 維護工具

logs/
├── neural_growth_log.json                 # 成長記錄
└── connection_usage.json                  # 連接統計

docs/
└── 自適應神經成長系統指南.md               # 完整文檔
```

## 💡 設計理念

### 為什麼要漸進式？

**傳統方式**（固定規模）：

```
❌ 數據少 → 過度擬合
❌ 數據多 → 能力不足
❌ 一次性調整 → 不穩定
```

**漸進式方式**（自適應）：

```
✅ 隨數據成長 → 按需擴展
✅ 頻繁路徑強化 → 效率提升
✅ 平滑過渡 → 穩定可靠
```

### 對數增長的優勢

使用 `log(1 + x)` 而非線性增長：

- 避免過度強化
- 保持學習能力
- 更穩定可控

## 🎓 深入學習

完整指南：`docs/自適應神經成長系統指南.md`

包含：

- 詳細技術原理
- 配置自定義方法
- 故障排除指南
- 最佳實踐建議

## 🔬 測試系統

```bash
# 測試自適應成長計算
python3 500/llama32-chat/learning/adaptive_neural_growth.py

# 測試連接強化邏輯
python3 500/llama32-chat/learning/progressive_connection_strengthening.py
```

## 🚀 開始使用

1. **啟動聊天系統**（已自動集成）
2. **正常使用**（系統會自動記錄和成長）
3. **定期查看**（`./view_neural_growth.sh`）
4. **週期維護**（`./maintain_neural_system.sh`）

系統會自己學習、自己成長、自己優化！

---

**創建日期**: 2026-03-03  
**狀態**: ✅ 已測試並集成  
**兼容性**: 與現有系統完全兼容

## 人工二次判讀標籤（2026-05-26）
- 主流程標籤：`training/neural-growth`
- 次流程標籤：`training/connection-strengthening`
- 正相關判定：是（直接描述連接增強機制，符合神經元式正增強）
- 處置：由中信心升級為訓練高信心。
- 神經連結：
  - [[07_MOC_訓練群組_2026-05-26]]
  - [[03_MOC_智能體關係強化與訓練分流]]
  - [[ProjectDocs/dev/AGENT_RELATIONSHIP_ENHANCEMENT_PLAYBOOK_2026-05-25]]

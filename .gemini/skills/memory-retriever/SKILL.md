---
name: memory-retriever
description: 本地對話記憶搜尋與提取工具。用於搜尋超過 1,300 條的 ChatGPT 歷史對話及本地知識庫，幫助您找回過去的技術細節與討論。
---

# Memory Retriever

您的「數位大腦」檢索器。

## Stability and Conflict Policy

1. 優先讀取記憶與知識資料，不直接修改原始記錄檔。
2. 若使用者同時要求「查詢 + 修復」，本技能只輸出檢索證據，寫入交由工程技能執行。
3. 自治守護模式下，允許讀取 `data_hdd_storage/autonomy/*.json` 作為任務上下文，但禁止改寫佇列狀態。

## 核心功能

1. **深度搜尋**：跨越 1,300+ 條對話記錄，尋找特定的關鍵字或技術主題。
2. **全文檢索**：不僅搜尋標題，更深入搜尋每條對話的內容。
3. **結果排序**：根據關鍵字匹配的相關性（出現頻率）進行排序。

## 如何使用

### 搜尋記憶

執行腳本並帶入關鍵字：

```bash
python3 scripts/search_memory.py "網路安全"
```

### 常見搜尋場景

- 尋找過去討論過的**特定代碼片段**。
- 找回某個**專案的初步構想**。
- 提取過去對**特定工具**（如 Ollama, Mistral）的配置建議。

## 資源

- **scripts/search_memory.py**: 高效搜尋引擎邏輯
- **data_hdd_storage/autonomy/**: 任務自治狀態快照

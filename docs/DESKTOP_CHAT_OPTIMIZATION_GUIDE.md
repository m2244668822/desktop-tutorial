# 桌面聊天軟體優化指南

> **操作說明（中文）**：多視窗／單一視窗啟動參數與檔案對照，見 [docs/桌面聊天使用說明.md](docs/桌面聊天使用說明.md)。

## 概述

本文件記錄對桌面聊天軟體的多項優化，包括對接狀態回報、AI 跳針問題改善、以及語言模型升級建議。

---

## 1. 對接與監控面板真實狀態回報

### 1.1 新增功能

#### 健康分數系統 (`health_score`)

- 計算方式：
  - Ollama 狀態：30分
  - API 金鑰：40分
  - VSCode 狀態：20分
  - 模型設定：10分

#### 對接狀態詳細資訊 (`docking`)

```json
{
  "vscode_connected": true/false,
  "workspace_detected": true/false,
  "api_healthy": true/false,
  "ollama_healthy": true/false,
  "overall": true/false
}
```

#### 即時監控指標 (`monitoring`)

- `message_count`: 訊息歷史數量
- `reply_count`: 回覆歷史數量
- `last_reply_time`: 最後回覆時間戳
- `context_depth`: 對話上下文深度

### 1.2 實作改動

**後端 (`desktop_chat_app.py`)**

- [`get_status()`](desktop_chat_app.py:67) - 新增詳細狀態回報
- [`_calculate_health_score()`](desktop_chat_app.py:166) - 健康分數計算
- [`_get_available_models()`](desktop_chat_app.py:195) - 可用模型列表查詢

**前端 (`templates/chat.html`)**

- 新增健康分數顯示區塊
- 新增對接狀態指示
- 新增即時監控指標
- 新增 CSS 樣式 (status-good, status-warn, status-error)

---

## 2. AI 溝通跳針問題改善

### 2.1 問題分析

原始系統可能產生重複性回覆，導致「跳針」現象。

### 2.2 改善方案

#### 2.2.1 增強系統提示詞

每個代理的系統提示詞現在包含：

- 每次回覆必須與上次不同
- 避免重複相同詞語或句子結構
- 加入時間戳記以區分

#### 2.2.2 回覆多樣性檢測 (`_diversify_reply()`)

```python
def _diversify_reply(self, reply: str, now_ts: float) -> str:
    # 檢查是否與最近回覆過於相似
    # 添加變化後綴（時間戳、序列號等）
```

#### 2.2.3 對話上下文追蹤

- 保留最近 3 組對話上下文
- 包含使用者訊息和助理回覆
- 用於改善回覆連貫性

#### 2.2.4 回覆歷史記錄

- 保留最近 5 次回覆
- 用於相似度檢測
- 超過 60 秒的歷史不受影響

---

## 3. 語言模型選擇建議

### 3.1 支援的模型清單

| 模型名稱     | 描述                     | 上下文長度 | 推薦   |
| ------------ | ------------------------ | ---------- | ------ |
| llama3.3:70b | Llama 3.3 70B - 最強效能 | 128K       | ✅     |
| llama3.2:90b | Llama 3.2 90B - 高效能   | 128K       |        |
| llama3.2:3b  | Llama 3.2 3B - 輕量快速  | 128K       | (預設) |
| qwen2.5:72b  | Qwen 2.5 72B - 中文優化  | 32K        |        |
| qwen2.5:14b  | Qwen 2.5 14B - 中文輕量  | 32K        |        |
| mistral:7b   | Mistral 7B - 均衡效能    | 8K         |        |
| phi4:14b     | Phi-4 14B - 微軟新模型   | 4K         |        |

### 3.2 模型切換方式

在 `500/llama32-chat/.env` 中設定：

```bash
OPEN_SOURCE_CHAT_MODEL=llama3.3:70b
# 或
OLLAMA_MODEL=qwen2.5:72b
```

### 3.3 效能優化建議

1. **中文任務**: 優先使用 `qwen2.5:72b` 或 `qwen2.5:14b`
2. **複雜推理**: 使用 `llama3.3:70b`
3. **輕量快速回覆**: 維持 `llama3.2:3b`

---

## 4. 開源專案參考

### 4.1 框架類

- **Microsoft Agent Framework**: 企業級 workflow/orchestration
- **LangGraph**: Stateful graph agent，工作流追蹤
- **OpenHands**: 軟體工程代理與實作任務
- **AutoGen**: 多代理協作框架
- **CrewAI**: 角色導向 crew/task
- **smolagents**: 輕量 code agent

### 4.2 評測資料

- **SWE-bench**: 工程問題解決與修復能力
- **WebArena-Verified**: Web 任務代理與工具調度

---

## 5. 使用方式

### 5.1 啟動桌面聊天

```bash
python desktop_chat_app.py
```

### 5.2 監控面板解讀

| 狀態    | 顏色         | 意義           |
| ------- | ------------ | -------------- |
| 🟢 綠色 | status-good  | 健康分數 ≥ 70  |
| 🟡 黃色 | status-warn  | 健康分數 40-69 |
| 🔴 紅色 | status-error | 健康分數 < 40  |

### 5.3 常用指令

| 指令         | 功能              |
| ------------ | ----------------- |
| 請研究員     | 召喚研究員回報    |
| 請工程師     | 召喚工程師回報    |
| 請中繼器     | 召喚中繼器回報    |
| 解決相關問題 | 一鍵執行全部優化  |
| 先查 API     | 檢查 API 連線狀態 |

---

## 6. 版本資訊

- **更新日期**: 2026-03-21
- **版本**: 2.0
- **主要改動**:
  - 新增健康分數系統
  - 改善 AI 跳針問題
  - 新增模型選擇支援
  - 增強監控面板顯示

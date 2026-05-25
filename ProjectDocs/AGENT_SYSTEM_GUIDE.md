# 🧠 智能體統一系統 - 完整使用指南

## 🚀 快速開始

### 一鍵啟動（推薦）

```bash
cd /Volumes/智能體/城城城程式
python3 ai_agent_launcher.py
```

會顯示菜單：

```
1️⃣   開始對話
2️⃣   查看學習統計
3️⃣   查看用戶檔案
4️⃣   診斷記憶系統
5️⃣   執行自主學習
0️⃣   退出
```

### 直接啟動對話

```bash
python3 start_groq_memory_chat.py
```

## ✨ 系統特點

### 1️⃣ **超強記憶系統**

- ✅ **13 個記憶源**整合
- ✅ **1,840+ 條記憶項目**
- ✅ **包含 1,324+ ChatGPT 對話**
- ✅ 468+ 知識庫條目
- ✅ 完整工作日誌和協作上下文

### 2️⃣ **個性化對話風格**

基於你在 ChatGPT 上設置的個性化提示詞：

**回答特徵：**

- 字數多但有複利效果
- 自動化、樹狀圖整理
- 主動提示和澄清
- 前瞻性、Z 世代風格

**用戶背景：**

- 26 歲、身心障礙者
- 社工、心理學者
- 分散式思考者
- 喜歡：學習、音樂、設計、宣傳

### 3️⃣ **智能主題識別**

系統自動識別 10 大領域：

- 🔥 AI/機器學習
- 🔥 編程
- 📊 數據分析
- 🎨 設計/創意
- 💼 工作流程
- 📚 記憶/知識
- 🔧 系統架構
- ⚙️ 優化
- 🧪 測試
- 📢 對話/通信

### 4️⃣ **自動學習分析**

每次對話結束自動：

- 📝 記錄對話內容
- 🧠 分析主題和品質
- 💡 提取學習見解
- 🚀 生成改進建議
- 📊 保存到學習日誌

## 📋 完整功能列表

### 對話系統

| 功能       | 文件                        | 說明                   |
| ---------- | --------------------------- | ---------------------- |
| 主對話系統 | `start_groq_memory_chat.py` | Groq AI + 完整記憶     |
| 自動啟動   | `setup_and_run.sh`          | 設置環境變數後啟動     |
| API 查找   | `find_api_key.py`           | 自動查找 GROQ API 密鑰 |

### 分析工具

| 功能         | 文件                         | 說明             |
| ------------ | ---------------------------- | ---------------- |
| 學習統計面板 | `view_learning_dashboard.py` | 查看所有學習記錄 |
| 用戶檔案分析 | `view_memory_profile.py`     | 分析個性和主題   |
| 記憶診斷     | `diagnose_memory.py`         | 檢查記憶源狀態   |
| 自主學習分析 | `agent_self_learning.py`     | 深度對話分析     |

### 統一啟動器

| 文件                   | 說明                           |
| ---------------------- | ------------------------------ |
| `ai_agent_launcher.py` | 🎯 **推薦使用** - 統一菜單界面 |

## 💡 使用場景

### 場景 1️⃣: 深入討論自由業規劃

```bash
python3 start_groq_memory_chat.py
# 提問：我的自由業收入結構應該如何規劃？
# 系統自動：
# 1. 調用你的完整背景
# 2. 用樹狀圖分類法
# 3. 整合心理學知識
# 4. 記錄為學習記錄
```

### 場景 2️⃣: 追蹤學習進度

```bash
python3 view_learning_dashboard.py
# 查看：
# - 過去的討論主題
# - 對話質量評分
# - 智能體學到的內容
# - 下次改進方向
```

### 場景 3️⃣: 檢查記憶完整性

```bash
python3 diagnose_memory.py
# 確認：
# - 13 個記憶源都已加載
# - 1,840+ 條記憶項目可用
# - 所有 ChatGPT 數據已整合
```

## 🔧 配置文件

### API 密鑰位置

- **自動檢測順序：**
  1. 環境變數 `GROQ_API_KEY`
  2. `.env` 文件
  3. 配置文件 `config/gemini_config.json`

### 記憶源位置

所有記憶來源位置配置在 `/tools/local_memory_api.py`：

```python
self.memory_sources = {
    "conversation_logs": "data/conversation_logs/...",
    "chatgpt_database": "500/llama32-chat/data/local_knowledge/...",
    "knowledge_base": "500/llama32-chat/data/local_knowledge/...",
    # ... 13 個源
}
```

## 📊 數據流向

```
對話輸入
   ↓
[個性化提示詞]
   ↓
[Groq AI 處理]
   ↓
[1,840+ 記憶上下文]
   ↓
[個性化回應]
   ↓
[自動保存]
   ↓
[自主學習分析]
   ↓
[學習記錄存檔]
```

## 🎯 性能指標

| 指標             | 數值             |
| ---------------- | ---------------- |
| **記憶容量**     | 1,840+ 項        |
| **ChatGPT 數據** | 1,324+ 對話      |
| **知識庫**       | 468+ 條          |
| **API 速度**     | Groq 快速推理    |
| **個性化度**     | 完全基於你的風格 |
| **學習追蹤**     | 自動記錄每次對話 |

## ❓ 常見問題

### Q: API 密鑰在哪裡？

A:

```bash
# GROQ API 在 .env 文件中：
cat /Volumes/智能體/城城城程式/500/llama32-chat/.env
```

### Q: 如何重新初始化記憶？

A:

```bash
# 診斷記憶狀態
python3 diagnose_memory.py

# 查看記憶加載進度
python3 agent_self_learning.py
```

### Q: 學習記錄保存在哪裡？

A:

```
logs/agent_learning_reflections.json  # 自主學習反思
data/conversation_logs/groq_session_*.json  # 對話日誌
```

### Q: 如何更改個性化風格？

A: 編輯 `start_groq_memory_chat.py` 中的 `SYSTEM_PERSONALITY` 常數

## 🚀 下一步改進

- [ ] 支持多輪對話的自動連續學習
- [ ] 生成學習報告（日/週/月統計）
- [ ] 整合實時反饋迴圈
- [ ] 添加對話質量評分系統
- [ ] 支持導出學習成果

## 📞 技術支持

所有日誌和診斷信息保存在：

- 📁 `/logs/` - 系統日誌
- 📁 `/data/conversation_logs/` - 對話記錄
- 📁 `/config/` - 配置文件

## ✅ 系統檢查清單

啟動前確認：

- [ ] GROQ 密鑰已設置
- [ ] 記憶文件存在（13 個源）
- [ ] 至少 1GB 可用空間

```bash
# 一鍵檢查
python3 diagnose_memory.py
```

---

**🎉 系統已準備就緒！執行 `python3 ai_agent_launcher.py` 開始使用**

# 🚀 系統設置與啟動全攻略 (System Setup & Launch)

> **整合日期**: 2026-04-28  
> **覆蓋文檔**: QUICK_START, QUICK_START_ZH, PLAN_C, GEMINI_SETUP_GUIDE

---

## 🔑 第一階段：API 密鑰配置

### 1. 獲取密鑰

- **Gemini (主要)**: 訪問 [Google AI Studio](https://aistudio.google.com/apikey) 獲取免費 Key。
- **Groq (次要/共讀模式)**: 訪問 Groq 控制面板。

### 2. 設置環境變數 (推薦)

在您的終端執行或加入 `~/.zshrc`:

```bash
export GEMINI_API_KEY='你的金鑰'
```

### 3. 使用配置文件 (備選)

編輯 `config/gemini_config.json`:

```json
{
  "api_key": "你的金鑰",
  "model": "gemini-2.0-flash"
}
```

---

## ⚡ 第二階段：啟動對話系統

本系統提供三種主要的互動模式：

| 模式             | 命令                                  | 適用場景                         |
| :--------------- | :------------------------------------ | :------------------------------- |
| **標準記憶模式** | `python3 start_gemini_memory_chat.py` | 整合 13 個本地記憶源，最聰明。   |
| **共讀模式**     | `python3 start_groq_memory_chat.py`   | 專注於即時摘要與學習，速度極快。 |
| **自動引導**     | `python3 auto_start_chat.py`          | 初次使用，自動檢測環境並啟動。   |

---

## 🛠️ 第三階段：環境驗證

如果啟動失敗，請執行以下診斷工具：

```bash
# 完整檢查環境、依賴與 API 連通性
python3 setup_gemini_complete.py

# 僅驗證 API Key
echo $GEMINI_API_KEY
```

---

## 🆘 常見問題 (FAQ)

- **Q: 為什麼加載記憶很慢？**  
  A: 系統正在索引超過 10,000 條對話，首次加載後會緩存。
- **Q: API 限制 (RPM) 是多少？**  
  A: 免費版 Gemini 為每分鐘 60 次請求，對於個人對話綽綽有餘。
- **Q: 記憶文件在哪裡？**  
  A: 主要存儲在 `data/conversations.json` 和 `config/chat_memory.json`。

---

_詳細技術細節請參考 [Gemini 設置詳解](GEMINI_SETUP_GUIDE.md)_

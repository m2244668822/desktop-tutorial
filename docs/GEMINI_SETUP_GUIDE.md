# 🚀 Gemini + 本地記憶統一對話系統 - 完整設置指南

## 📋 系統概述

這是一個整合了 **Gemini AI** 和 **所有本地記憶** 的統一對話系統。

### 核心特性

✅ **Gemini 2.0 Flash 集成**

- 超快的 AI 回應
- 免費額度充足 (60 RPM)
- 支持 150+ 語言

✅ **完整的本地記憶支援**

- **ChatGPT 完整數據庫**: 1,324+ 條對話，15,154+ 條消息
- **系統對話記錄**: 所有應用程序交互記錄
- **知識庫**: 完整的索引和洞察
- **數據源**: 13 個不同的記憶源

✅ **自動記憶上下文**

- 每次對話都會加載相關記憶
- Gemini 基於完整歷史做出更智能的決定

---

## 🔑 第 1 步：獲取 Gemini API 密鑰

### 方式 A：網頁獲取（推薦）

1. 訪問 [Google AI Studio](https://aistudio.google.com/apikey)
2. 使用 Google 帳號登入
3. 點擊 **"Create API Key"** 按鈕
4. 選擇 **"Create API key in new project"**
5. 複製顯示的 API 密鑰

### 方式 B：使用 Google Cloud Console

1. 訪問 [Google Cloud Console](https://console.cloud.google.com/)
2. 創建新項目或選擇現有項目
3. 啟用 Generative AI API
4. 創建 API 密鑰

---

## 🔧 第 2 步：設置 API 密鑰

### 選項 1：交互式設置（最簡單）

```bash
cd /Volumes/智能體/城城城程式
python3 setup_gemini_complete.py
```

然後選擇 **"1) 快速設置"** 並按照提示操作。

### 選項 2：環境變數設置

#### 臨時設置（當前終端有效）：

```bash
export GEMINI_API_KEY='your-api-key-here'
```

#### 永久設置（推薦）：

**針對 macOS (zsh)**：

```bash
echo "export GEMINI_API_KEY='your-api-key-here'" >> ~/.zshrc
source ~/.zshrc
```

**針對 macOS (bash)**：

```bash
echo "export GEMINI_API_KEY='your-api-key-here'" >> ~/.bash_profile
source ~/.bash_profile
```

**驗證設置：**

```bash
echo $GEMINI_API_KEY
```

如果看到您的密鑰前幾個字符，則表示設置成功。

### 選項 3：配置文件設置

建立或編輯配置文件：

```bash
cat > /Volumes/智能體/城城城程式/config/gemini_config.json << 'EOF'
{
    "api_key": "your-api-key-here",
    "model": "gemini-2.0-flash"
}
EOF
```

設置文件權限（安全）：

```bash
chmod 600 /Volumes/智能體/城城城程式/config/gemini_config.json
```

---

## ✅ 第 3 步：驗證設置

```bash
# 快速驗證所有設置
bash /Volumes/智能體/城城城程式/quick_start.sh

# 或使用完整驗證工具
python3 /Volumes/智能體/城城城程式/setup_gemini_complete.py
# 然後選擇 "4) 驗證設置"
```

**預期輸出：**

```
✅ Python 3.x.x
✅ GEMINI_API_KEY 已設置
✅ google-generativeai 已安裝
✅ 本地記憶 API 就緒
✅ 所有檢查完成！
```

---

## 🚀 第 4 步：啟動對話

```bash
cd /Volumes/智能體/城城城程式
python3 start_gemini_memory_chat.py
```

### 對話系統會執行：

1. ✅ 初始化 Gemini API
2. ✅ 加載所有本地記憶（13 個源）
3. ✅ 構建用戶背景信息上下文
4. ✅ 開始互動對話

### 使用技巧：

- **開始對話**：只需輸入任何問題
- **查看背景信息**：系統會自動引入相關記憶
- **退出對話**：輸入 `/bye` 或 `exit`
- **查看對話記錄**：自動保存到 `data/conversation_logs/`

---

## 📊 本地記憶源詳解

系統加載的 **13 個記憶源**：

| 來源           | 描述                    | 條數   |
| -------------- | ----------------------- | ------ |
| ChatGPT 數據庫 | 完整的 ChatGPT 對話歷史 | 1,324+ |
| 系統對話記錄   | 所有應用程序交互        | 1000+  |
| 知識庫         | 提取的知識項目          | 5000+  |
| 會話數據       | 用戶會話記錄            | 100+   |
| 協作上下文     | 團隊協作信息            | 50+    |
| Agent 日誌     | AI Agent 工作日誌       | 100+   |
| 收入記錄       | 平台收入數據            | 200+   |
| 優化記錄       | 系統優化歷史            | 50+    |
| Bug 追蹤       | 代碼問題記錄            | 100+   |
| ...            | ...                     | ...    |

**總計**: 10,000+ 條記憶項

---

## 🔒 安全須知

### API 密鑰管理

⚠️ **重要**：API 密鑰是敏感信息

✅ **該做：**

- 保密保管 API 密鑰
- 定期更換密鑰
- 只在安全的計算機上使用
- 在需要時禁用密鑰

❌ **不該做：**

- 分享密鑰給他人
- 上傳到公開 GitHub
- 在終端歷史中暴露
- 在代碼註釋中包含

### 配置文件保護

```bash
# 確保配置文件權限為 600 (只有所有者可讀)
chmod 600 /Volumes/智能體/城城城程式/config/gemini_config.json

# 將配置文件加入 .gitignore
echo "config/gemini_config.json" >> .gitignore
```

---

## 🆘 故障排除

### 問題 1：API 密鑰未被找到

```bash
# 檢查環境變數
echo $GEMINI_API_KEY

# 檢查配置文件
cat /Volumes/智能體/城城城程式/config/gemini_config.json

# 重新設置
export GEMINI_API_KEY='your-api-key-here'
```

### 問題 2：Google Generative AI 庫未安裝

```bash
# 安裝
pip install google-generativeai

# 或升級
pip install --upgrade google-generativeai
```

### 問題 3：本地記憶加載失敗

```bash
# 檢查本地記憶 API
cd /Volumes/智能體/城城城程式
python3 -c "from tools.local_memory_api import LocalMemoryAPI; api = LocalMemoryAPI(); print('OK')"
```

### 問題 4：無法連接到 Gemini

```bash
# 檢查網絡連接
ping aistudio.google.com

# 檢查 API 配額
# 訪問: https://aistudio.google.com/apikey
# 查看今日使用情況
```

---

## 📈 使用統計

### API 配額（免費層）

- **每分鐘請求數 (RPM)**: 60
- **每日限制**: 1,000 次生成調用
- **文本長度**: 30K 文本 tokens/分鐘

### 本地記憶容量

目前系統支持：

- 最多 **100,000+ 條記憶項**
- 每個對話最多引入 **100 條最相關記憶**
- 平均每次對話加載 **50 條記憶上下文**

---

## 🎯 後續步驟

### 立即可做：

1. ✅ 設置 API 密鑰
2. ✅ 驗證系統配置
3. ✅ 啟動對話系統
4. ✅ 開始與 Gemini 交互

### 進階功能（規劃中）：

- 🔄 自動學習和記憶優化
- 📊 對話分析儀表板
- 🤖 多模型無縫切換
- 💾 對話備份和恢復

---

## 📞 支持和反饋

如遇問題，請參考：

- 📖 本指南的故障排除部分
- 🔗 [Google AI Studio 文檔](https://ai.google.dev/)
- 💬 在應用中使用 `/help` 命令

---

## 📝 版本信息

- **系統版本**: 1.0.0
- **Gemini API**: 2.0-flash
- **本地記憶源**: 13 個
- **更新日期**: 2026-03-01

---

**祝您使用愉快！🎉**

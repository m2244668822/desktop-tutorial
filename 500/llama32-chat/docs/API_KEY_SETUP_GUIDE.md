# 🔐 API_KEY 設置指南

## ⚠️ 當前問題

系統檢測到 OpenAI API_KEY 未設定。異常通報：

```
[智能體異常通報] 2026-02-28T09:36:16.854518
類型：task_error
嚴重性：warning
詳情：{'model': 'openai', 'error_type': 'ConfigError', 'error_message': 'API_KEY 未設定'}
```

## ✅ 解決方案

### 步驟 1：複製環境變數範本

進入配置目錄並複製 `.env.example` 為 `.env`：

```bash
cd /Volumes/智能體/城城城程式/500/llama32-chat/config
cp .env.example .env
```

### 步驟 2：獲取各個 AI 模型的 API Keys

#### 🔵 **Google Gemini** (推薦 - 免費額度充足)

1. 訪問：https://ai.google.dev/
2. 點擊 "Get API Key"
3. 在 Google Cloud Console 創建項目（如需要）
4. 複製 API Key 並填入 `.env`：
   ```
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

#### 🟠 **OpenAI (GPT)** (需付費)

1. 訪問：https://platform.openai.com/api-keys
2. 登入或創建 OpenAI 賬戶
3. 點擊 "Create new secret key"
4. 複製 API Key 並填入 `.env`：
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```
5. **設置付費方式**：https://platform.openai.com/account/billing/overview

#### 🤖 **Claude (Anthropic)** (有限免費額度)

1. 訪問：https://console.anthropic.com/
2. 登入並創建 API Key
3. 複製 API Key 並填入 `.env`：
   ```
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

#### 🚀 **xAI (Grok)** (需付費)

1. 訪問：https://console.x.ai/
2. 登入 X.AI 賬戶
3. 創建 API Key
4. 複製並填入 `.env`：
   ```
   XAI_API_KEY=your_xai_api_key_here
   ```

### 步驟 3：編輯 `.env` 文件

使用文本編輯器打開 `.env`：

```bash
nano config/.env
```

或在 VS Code 中打開：

```bash
code config/.env
```

### 步驟 4：填入 API Keys

完整的 `.env` 文件示例：

```dotenv
# Gemini (推薦使用)
GEMINI_API_KEY=AIzaSy...你的實際金鑰...

# OpenAI (可選)
OPENAI_API_KEY=sk-proj-...你的實際金鑰...

# Claude (可選)
ANTHROPIC_API_KEY=sk-ant-...你的實際金鑰...

# xAI (可選)
XAI_API_KEY=xai-...你的實際金鑰...

# Ollama (本地)
OLLAMA_URL=http://localhost:11434/api/chat
```

## 🛡️ 安全提示

⚠️ **重要**：

- ❌ **永遠不要**將 API Key 提交到 Git
- ❌ **永遠不要**在代碼中硬編碼 API Key
- ✅ `.env` 文件已添加到 `.gitignore`
- ✅ 只在本地機器上設置
- ✅ 定期輪換 API Key
- ✅ 設置 API Key 的使用配額限制

## 💰 成本考慮

| 模型       | 成本            | 推薦用途               |
| ---------- | --------------- | ---------------------- |
| **Gemini** | 免費 + 付費選項 | 👍 首選（免費額度大）  |
| **Ollama** | 免費（本地）    | 👍 最經濟（無API成本） |
| **OpenAI** | 按量計費        | 💰 功能強大但成本高    |
| **Claude** | 有限免費 + 付費 | 💰 優質但成本中等      |
| **xAI**    | 按量計費        | 💰 新模型較貴          |

## 🔄 最小化成本的策略

1. **優先使用免費選項**：

```python
# 系統會自動優先選擇 Ollama（本地免費）
# 然後選擇 Gemini（免費額度大）
# 最後才使用付費模型
```

2. **設置使用配額**：

在各 API 平台設置月度消費限制：

- **OpenAI**: https://platform.openai.com/account/billing/limits
- **Google Cloud**: GCP Console → 帳單 → 預算提醒
- **Anthropic**: https://console.anthropic.com/settings

3. **靈活選擇模型**：

系統支持自動故障轉移，會在模型失敗時嘗試其他選項：

```
首選 Ollama → Gemini → Claude → OpenAI → xAI
```

## 🧪 驗證設置

### 測試 API Keys 是否生效

運行驗證腳本：

```bash
python -c "
import os
from dotenv import load_dotenv

load_dotenv('config/.env')

print('🔍 已加載的 API Keys：')
print(f'✅ GEMINI: {\"已設定\" if os.getenv(\"GEMINI_API_KEY\") else \"❌ 未設定\"}')
print(f'✅ OPENAI: {\"已設定\" if os.getenv(\"OPENAI_API_KEY\") else \"❌ 未設定\"}')
print(f'✅ ANTHROPIC: {\"已設定\" if os.getenv(\"ANTHROPIC_API_KEY\") else \"❌ 未設定\"}')
print(f'✅ XAI: {\"已設定\" if os.getenv(\"XAI_API_KEY\") else \"❌ 未設定\"}')
"
```

#### 預期輸出

```
🔍 已加載的 API Keys：
✅ GEMINI: 已設定
✅ OPENAI: 已設定
✅ ANTHROPIC: 已設定
✅ XAI: 已設定
```

### 測試模型連接

啟動互動模式測試：

```bash
python core/chat.py --interactive
```

嘗試：

1. 輸入一般問題（使用默認模型）
2. 輸入 `model openai` 切換到 OpenAI
3. 輸入 `model gemini` 切換到 Gemini

## 📋 故障排除

### 問題 1：仍然出現 ConfigError

**解決方案**：

```bash
# 檢查 .env 文件是否存在
ls -la config/.env

# 檢查文件有無語法錯誤
cat config/.env | head -20
```

### 問題 2：API Key 無效

**解決方案**：

1. 驗證 API Key 沒有空格或換行
2. 確保使用了最新生成的 Key（舊 Key 可能已過期）
3. 檢查 API Key 配額是否已用盡

### 問題 3：無法連接到 API

**解決方案**：

1. 檢查網絡連接
2. 確認 API 服務狀況：
   - OpenAI: https://status.openai.com/
   - Google Gemini: Google Cloud 狀態頁
   - Anthropic: https://status.anthropic.com/

### 問題 4：多個 API 都無法使用

**解決方案**：

使用本地 **Ollama** 替代（不需要 API Key）：

```bash
# 1. 安裝 Ollama
# https://ollama.ai/

# 2. 拉取模型
ollama pull llama2

# 3. 啟動服務
ollama serve

# 4. 啟動聊天
python core/chat.py --interactive
```

## 🎓 學習記錄

此指南已記入系統學習：

- **主題**：OpenAI API_KEY 配置異常
- **異常類型**：ConfigError
- **解決方案**：19 個步驟的完整設置指南
- **相關文件**：config/.env.example

## 📚 相關文檔

- [context_fix_README.md](CONTEXT_FIX_README.md) - 對話上下文保持功能
- [README.md](README.md) - 系統概述
- [docs/](docs/) - 完整文檔

## ✅ 檢查清單

使用此清單確保所有設置正確：

- [ ] 已複製 `.env.example` 為 `.env`
- [ ] 至少添加了一個 API Key (推薦 Gemini)
- [ ] API Key 格式正確（無多餘空格）
- [ ] `.env` 文件位於 `config/` 目錄
- [ ] 已於安全位置備份 API Keys
- [ ] 已設置 API 配額限制
- [ ] 已運行驗證腳本確認設置
- [ ] 驗證成功後，可啟動互動模式

## 🚀 開始使用

設置完成後，立即啟動系統：

```bash
# 進入主目錄
cd /Volumes/智能體/城城城程式/500/llama32-chat

# 啟動互動模式
python core/chat.py --interactive
```

祝您使用愉快！🎉

---

**文檔版本**: 1.0  
**最後更新**: 2026-02-28  
**狀態**: ✅ 已驗證並可用

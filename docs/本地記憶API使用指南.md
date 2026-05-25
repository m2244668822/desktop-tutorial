# 本地記憶 API 使用指南

## Local Memory API - 統一訪問接口

---

## 📋 系統概述

本地記憶 API 提供統一接口，讓任何語言模型（Gemini, Claude, ChatGPT, 本地 Mistral/Llama）都能訪問和提取您的本地對話記憶。

### 核心功能

✅ **統一數據訪問** - 整合 5 個不同的對話記憶存儲源  
✅ **跨模型兼容** - 支持 OpenAI、Anthropic、Google、本地模型格式  
✅ **快速檢索** - 內建緩存機制，5分鐘緩存週期  
✅ **靈活搜索** - 支持關鍵詞、日期範圍、數據源過濾  
✅ **命令行工具** - 快速訪問與測試

---

## 🚀 快速開始

### 1. 查看記憶總結

```bash
python3 tools/local_memory_api.py --summary
```

**輸出示例**：

```json
{
  "total_conversations": 19,
  "by_source": {
    "conversation_logs": 4,
    "optimizations": 6,
    "bug_tracker": 1,
    "main_conversations": 7,
    "chat_memory": 1
  },
  "by_date": {
    "2026-03-01": 11,
    "2026-02-28": 8
  }
}
```

### 2. 查看最新對話

```bash
# 查看最新 10 條（默認）
python3 tools/local_memory_api.py

# 查看最新 20 條
python3 tools/local_memory_api.py --latest 20
```

### 3. 搜索對話

```bash
# 搜索包含 "履歷" 的對話
python3 tools/local_memory_api.py --search "履歷"

# 搜索包含 "效能升級" 的對話
python3 tools/local_memory_api.py --search "效能升級"
```

### 4. 測試本地模型

```bash
python3 tools/local_memory_api.py --test-ollama
```

**輸出示例**：

```json
{
  "ollama_installed": true,
  "models_available": ["mistral:latest", "llama3.2:latest"],
  "connection_status": "connected"
}
```

---

## 🔌 為不同模型導出記憶

### OpenAI 格式 (ChatGPT)

```bash
python3 tools/local_memory_api.py --export openai --latest 20
```

**輸出格式**：

```json
[
  {
    "role": "user",
    "content": "用戶輸入內容"
  },
  {
    "role": "assistant",
    "content": "助手回應內容"
  }
]
```

**使用方式**：

```python
import openai

# 載入本地記憶
memory = get_exported_memory()  # 從 API 獲取

# 發送請求時包含記憶
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=memory + [
        {"role": "user", "content": "新問題"}
    ]
)
```

### Anthropic 格式 (Claude)

```bash
python3 tools/local_memory_api.py --export anthropic --latest 20
```

**輸出格式**：

```
以下是用戶的對話記憶：

對話 1:
用戶: 用戶輸入內容
助手: 助手回應內容

對話 2:
...
```

**使用方式**：

```python
import anthropic

client = anthropic.Anthropic()
memory_text = get_exported_memory()  # 從 API 獲取

response = client.messages.create(
    model="claude-3-opus-20240229",
    messages=[
        {
            "role": "user",
            "content": f"{memory_text}\n\n新問題：..."
        }
    ]
)
```

### Google 格式 (Gemini)

```bash
python3 tools/local_memory_api.py --export google --latest 20
```

**輸出格式**：

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [{ "text": "用戶輸入" }]
    },
    {
      "role": "model",
      "parts": [{ "text": "模型回應" }]
    }
  ]
}
```

**使用方式**：

```python
import google.generativeai as genai

memory = get_exported_memory()  # 從 API 獲取
model = genai.GenerativeModel('gemini-pro')

# 使用記憶進行對話
chat = model.start_chat(history=memory["contents"])
response = chat.send_message("新問題")
```

### 本地模型格式 (Mistral/Llama)

```bash
python3 tools/local_memory_api.py --export local --latest 20
```

**輸出格式**：

```
=== 本地對話記憶 ===

[2026-03-01T10:28:55.777436]
用戶: 好了，智能體接下來換你工作了...
助手: 根據授權立即啟動了完整的自動化工作系統...

------------------------------------------------------------
```

**使用方式**：

```bash
# 方式 1: 直接用 Ollama
python3 tools/local_memory_api.py --export local > /tmp/memory.txt
ollama run mistral "$(cat /tmp/memory.txt) 新問題：..."

# 方式 2: 使用 API
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "記憶內容 + 新問題",
  "stream": false
}'
```

---

## 💻 Python API 使用

### 基本使用

```python
from tools.local_memory_api import LocalMemoryAPI

# 初始化 API
api = LocalMemoryAPI()

# 獲取所有對話
all_conversations = api.get_all_conversations()
print(f"總共 {len(all_conversations)} 條對話")

# 獲取最新對話
latest = api.get_latest_conversations(count=10)
for conv in latest:
    print(f"{conv['timestamp']}: {conv['user_input']}")

# 搜索對話
results = api.search_conversations(
    query="履歷",
    start_date="2026-03-01",
    limit=20
)
print(f"找到 {len(results)} 條相關對話")

# 獲取系統總結
summary = api.get_memory_summary()
print(f"數據源: {summary['data_sources']}")
print(f"總對話數: {summary['total_conversations']}")
```

### 為模型導出

```python
# 為 OpenAI 導出
openai_format = api.export_for_model(
    model_type="openai",
    recent_count=20,
    include_metadata=False
)

# 為 Claude 導出
claude_format = api.export_for_model(
    model_type="anthropic",
    recent_count=20
)

# 為 Gemini 導出
gemini_format = api.export_for_model(
    model_type="google",
    recent_count=20
)

# 為本地模型導出
local_format = api.export_for_model(
    model_type="local",
    recent_count=20,
    include_metadata=True
)
```

### 測試 Ollama 連接

```python
# 檢查本地模型狀態
status = api.test_ollama_connection()

if status['ollama_installed']:
    print("✅ Ollama 已安裝")
    print(f"可用模型: {status['models_available']}")
else:
    print("❌ Ollama 未安裝")
```

---

## 🗂️ 數據源說明

系統整合以下 5 個對話記憶存儲源：

| 數據源               | 路徑                                                 | 說明         |
| -------------------- | ---------------------------------------------------- | ------------ |
| `conversation_logs`  | `data/conversation_logs/conversations_20260301.json` | 主要對話記錄 |
| `chat_memory`        | `config/chat_memory.json`                            | 舊版對話記憶 |
| `main_conversations` | `data/conversations.json`                            | 通用對話存儲 |
| `optimizations`      | `data/conversation_logs/optimizations.json`          | 系統優化記錄 |
| `bug_tracker`        | `data/conversation_logs/bug_tracker.json`            | Bug 追蹤記錄 |

所有數據源會被自動整合並標準化為統一格式。

---

## 🔧 啟動本地模型

### 方式 1: 命令行直接啟動

```bash
# 啟動 Mistral
ollama run mistral

# 啟動 Llama 3.2
ollama run llama3.2
```

### 方式 2: 使用 Python

```python
import subprocess

# 啟動對話
process = subprocess.Popen(
    ['ollama', 'run', 'mistral'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True
)

# 發送問題（包含記憶）
memory = api.export_for_model('local', recent_count=10)
question = "根據我的對話記憶，總結我最近的工作重點"
prompt = f"{memory}\n\n{question}"

stdout, stderr = process.communicate(input=prompt)
print(stdout)
```

### 方式 3: 使用 API 服務器

```bash
# 啟動 Ollama API 服務（通常自動運行）
ollama serve

# 使用 API
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "你的問題 + 記憶內容",
  "stream": false
}'
```

---

## 📊 實際使用案例

### 案例 1: 讓 ChatGPT 了解您的本地記憶

```python
from tools.local_memory_api import LocalMemoryAPI
import openai

api = LocalMemoryAPI()

# 獲取最近 20 條對話記憶
memory_messages = json.loads(
    api.export_for_model('openai', recent_count=20)
)

# 添加新問題
memory_messages.append({
    "role": "user",
    "content": "根據我的對話記憶，幫我總結最近的工作進度"
})

# 發送給 ChatGPT
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=memory_messages
)

print(response.choices[0].message.content)
```

### 案例 2: 讓本地 Mistral 訪問完整記憶

```bash
#!/bin/bash
# quick_chat_with_memory.sh

# 導出記憶
python3 tools/local_memory_api.py --export local --latest 30 > /tmp/memory.txt

# 啟動對話
echo "記憶已載入，您可以開始對話..."
ollama run mistral "$(cat /tmp/memory.txt)

請根據以上記憶回答問題。現在我的問題是：$1"
```

使用：

```bash
./quick_chat_with_memory.sh "我最近做了哪些關於履歷的工作？"
```

### 案例 3: 跨模型知識傳遞

```python
# 從本地模型獲取分析
local_analysis = query_local_model("分析我的對話記憶")

# 讓 Claude 進一步優化
claude_response = query_claude(
    f"以下是本地模型的分析：{local_analysis}\n"
    f"請提供更深入的見解和建議。"
)

# 記錄回 ChatGPT
chatgpt_summary = query_chatgpt(
    f"總結以下分析：{claude_response}"
)

print(chatgpt_summary)
```

---

## 🛠️ 故障排除

### 問題 1: Ollama 未安裝

**錯誤**：`ollama_installed: false`

**解決**：

```bash
# macOS
brew install ollama

# Linux
curl https://ollama.ai/install.sh | sh
```

### 問題 2: 模型未下載

**錯誤**：`models_available: []`

**解決**：

```bash
# 下載 Mistral
ollama pull mistral

# 下載 Llama 3.2
ollama pull llama3.2
```

### 問題 3: 記憶數據為空

**錯誤**：`total_conversations: 0`

**原因**：對話記錄文件不存在或為空

**解決**：

```bash
# 檢查文件是否存在
ls -lh data/conversation_logs/
ls -lh config/chat_memory.json

# 使用對話記錄系統記錄新對話
python3 -c "
from tools.local_memory_api import LocalMemoryAPI
api = LocalMemoryAPI()
print(api.get_memory_summary())
"
```

### 問題 4: 緩存未更新

**症狀**：新對話沒有出現在查詢結果中

**解決**：

```python
# 強制刷新緩存
api.get_all_conversations(refresh=True)
```

---

## 📈 性能優化建議

### 1. 使用緩存

```python
# 第一次調用會載入數據
api.get_all_conversations()  # 較慢

# 5分鐘內的後續調用使用緩存
api.get_all_conversations()  # 很快
```

### 2. 限制搜索範圍

```python
# 指定日期範圍
results = api.search_conversations(
    query="關鍵詞",
    start_date="2026-03-01",
    end_date="2026-03-01",
    limit=50
)
```

### 3. 選擇合適的導出數量

```python
# 只導出必要的對話數量
api.export_for_model('openai', recent_count=10)  # 快
api.export_for_model('openai', recent_count=100) # 慢
```

---

## 🔮 未來擴展

計劃中的功能：

- [ ] RESTful API 服務器（Flask/FastAPI）
- [ ] Web 界面儀表板
- [ ] 實時對話同步
- [ ] 向量化搜索（語義搜索）
- [ ] 多用戶支持
- [ ] 對話摘要與壓縮
- [ ] 自動標籤分類

---

## 📞 支持與反饋

如有問題或建議，請查看：

- 系統日誌：`data/conversation_logs/`
- 優化記錄：`data/conversation_logs/optimizations.json`

---

_文檔更新日期: 2026年3月1日_

## 人工二次判讀標籤（2026-05-26）
- 主流程標籤：`arch/memory-api`
- 次流程標籤：`training/memory-retrieval`
- 正相關判定：是（是模型與記憶層的接口契約，對回覆質量有實際增強）
- 處置：升級為架構+訓練雙核心標籤。
- 神經連結：
  - [[05_MOC_架構群組_2026-05-26]]
  - [[07_MOC_訓練群組_2026-05-26]]
  - [[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]

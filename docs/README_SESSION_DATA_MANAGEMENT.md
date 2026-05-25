# 🗂️ 會話數據管理系統 - 完整指南

## 📋 概述

會話數據管理系統是中樞神經的核心功能，實現了：

✅ **及時記錄** - 每次對話立即記錄到系統
✅ **定期驗證** - 10分鐘後自動驗證是否正確記錄
✅ **智能清理** - 自動識別和清理廢棄數據（臨時文件）
✅ **結構保護** - 按文件夾分類清理，保持組織結構

## 🎯 核心特性

### 1. 實時記錄機制

**工作流程**：

```
用戶輸入消息
    ↓
AI 生成回復
    ↓
記錄到本地記憶 (chat_memory.json)
    ↓
記錄到學習系統 (conversations.json)
    ↓
記錄到會話管理系統 (session_tracking.json)
    ↓
✅ 完成
```

**記錄內容**：

- 用戶消息
- AI 回複
- 時間戳
- 上下文信息（API、標籤等）
- 記錄狀態

### 2. 10分鐘定期驗證

**自動驗證**：

- 後台線程每10分鐘執行一次
- 檢查最近10分鐘記錄的會話
- 驗證記錄的完整性
- 生成驗證報告

**驗證項目**：

- ✅ 必要字段是否存在
- ✅ 消息內容是否合理
- ✅ 時間戳是否有效
- ✅ 上下文信息是否完整

### 3. 廢棄數據識別

**識別方式**：

- 匹配臨時文件模式 (_.tmp, _\_backup._, _.log 等)
- 檢查文件重要度評分
- 確認臨時/測試屬性

**廢棄文件類型**：

```
臨時文件    -> *.tmp, *.tmp.*, *_temp*
備份文件    -> *_backup.*, *.bak
日誌文件    -> *.log, *.logs
緩存文件    -> *.cache, __pycache__
測試文件    -> *_test.*, test_*
```

### 4. 文件夾結構保護

**核心原則**：

```
❌ 不刪除文件夾
✅ 只刪除不需要的文件
✅ 保持原有目錄結構
✅ 保護重要文件和數據
```

**受保護文件**：

- message.txt
- chat_memory.json
- conversations.json
- learning_log.json
- .env
- chat_client.py
- chat.py
- unified_learning_hub.py
- autonomous_agent.py

## 🚀 使用方法

### 方法1：命令行工具（推薦）

```bash
python session_data_manager_tool.py
```

**菜單選項**：

1. **查看驗證狀態** - 查看會話記錄驗證進度
2. **查看清理建議** - 按文件夾查看廢棄文件
3. **模擬清理** - 預覽將刪除哪些文件
4. **執行清理** - 實際刪除廢棄文件
5. **生成報告** - 生成完整數據管理報告

### 方法2：Python API

```python
from autonomous_agent import autonomous_agent

# 記錄對話會話
session_id = autonomous_agent.record_conversation_session(
    user_message="用戶消息",
    ai_response="AI回複",
    context={
        'api_used': 'gemini',
        'source': 'chat_client',
        'tags': ['coding', 'learning']
    }
)

# 查看驗證狀態
status = autonomous_agent.get_session_verification_status()
print(f"驗證率: {status['verification_rate']}")

# 查看清理建議
recommendations = autonomous_agent.get_cleanup_recommendations()
print(recommendations['recommendations_by_folder'])

# 分析清理（干運行）
result = autonomous_agent.analyze_and_cleanup_trash(dry_run=True)
print(f"可刪除: {result['deletion_summary']['total_files']} 個")

# 生成報告
report = autonomous_agent.generate_data_management_report()
print(report)
```

### 方法3：集成到應用

```python
# 在 chat_client.py 中自動調用
autonomous_agent.record_conversation_session(
    user_message=user_input,
    ai_response=ai_output,
    context={'source': 'chat_client'}
)
```

## 📊 系統狀態監控

### 驗證狀態

```
═══════════════════════════════════════════════════
📊 會話驗證狀態
═══════════════════════════════════════════════════

✅ 總會話數: 15
✅ 已驗證: 12
⏳ 待驗證: 3
📈 驗證率: 80.0%

📋 最近驗證:
  時間: 2026-02-28 07:25:00
  驗證會話數: 5
  識別的廢棄文件: 8 個
```

### 清理建議

```
📁 按文件夾分類的清理建議 (3 個文件夾):

📂 500/llama32-chat/data
   廢棄文件: 3 個 (450.25 KB)
   行動: 可安全刪除（仅刪除文件，保持文件夾結構）

📂 本地/opai本地
   廢棄文件: 5 個 (1024.50 KB)
   行動: 可安全刪除

📂 .venv/lib/python3.14/site-packages
   廢棄文件: 45 個 (2048.75 KB)
   行動: 可安全刪除
```

## 🎯 操作指南

### 場景1：查看會話記錄驗證進度

```bash
python session_data_manager_tool.py
# 選擇: 1
```

**輸出**：

- 總會話數
- 已驗證會話數
- 驗證率百分比
- 最近驗證時間

### 場景2：預覽可刪除文件

```bash
python session_data_manager_tool.py
# 選擇: 3
```

**輸出**：

- 廢棄文件清單
- 文件夾位置
- 文件大小
- 刪除原因

### 場景3：執行清理

```bash
python session_data_manager_tool.py
# 選擇: 4
# 輸入: yes
```

**執行流程**：

1. 掃描識別廢棄文件
2. 確認刪除列表
3. 按文件夾清理
4. 生成清理報告

### 場景4：定期檢查系統狀態

```bash
python session_data_manager_tool.py
# 選擇: 5
```

**生成報告**：

- 對話記錄統計
- 驗證進度
- 清理歷史
- 建議

## 📈 數據流轉

```
對話發生
   ↓
chat_client.py save_memory()
   ├─→ 保存到 chat_memory.json
   ├─→ 記錄到 conversations.json (ConversationLogger)
   └─→ 記錄到 session_tracking.json (SessionDataManager)
   ↓
10分鐘後
   ├─→ 自動驗證記錄完整性
   ├─→ 生成驗證報告
   └─→ 識別廢棄數據
   ↓
需要時
   ├─→ 用戶查看清理建議
   ├─→ 執行模擬清理預覽
   └─→ 實際刪除廢棄文件
```

## 🛡️ 安全機制

### 1. 文件保護

受保護的核心文件**不會被刪除**：

- 對話記錄
- 學習數據
- 配置文件
- 重要源代碼

### 2. 雙重確認

實際刪除前：

- 先進行模擬清理（干運行）
- 展示將刪除的文件列表
- 需要用戶明確確認

### 3. 分類感知

遵守文件夾結構：

- 按來源分類識別
- 按類別記錄清理
- 保持組織整潔

## 📚 技術詳情

### 文件位置

```
500/llama32-chat/data/
├── session_tracking.json        # 會話追蹤記錄
├── cleanup_log.json             # 清理日誌
└── verification_report.json     # 驗證報告
```

### 數據結構

**會話記錄**：

```json
{
  "session_id": "session_20260228_071234",
  "timestamp": "2026-02-28T07:12:34.567890",
  "user_message": "...",
  "ai_response": "...",
  "message_length": 256,
  "context": {...},
  "recorded_time": "2026-02-28T07:12:34.567890",
  "verified": true,
  "verification_time": "2026-02-28T07:22:34.567890",
  "is_trash": false,
  "cleanup_status": "verified"
}
```

**清理記錄**：

```json
{
  "timestamp": "2026-02-28T07:25:00",
  "dry_run": false,
  "trash_detected": [...],
  "deletion_summary": {
    "total_files": 8,
    "total_size": 1024000,
    "by_category": {...}
  }
}
```

## 🔧 配置選項

### 自動驗證週期

方式：編輯 `session_data_manager.py`

```python
time.sleep(600)  # 改為其他秒數
# 10分鐘 = 600秒
# 5分鐘 = 300秒
# 30分鐘 = 1800秒
```

### 廢棄文件模式

方式：修改 `_identify_trash_files()` 方法

```python
temp_patterns = [
    ('*.tmp', 'temporary', 1),
    ('*_backup.*', 'temporary', 2),
    # 添加新的模式...
]
```

## 📋 最佳實踐

### ✅ 推薦做法

1. **每週檢查一次**

   ```bash
   python session_data_manager_tool.py
   # 選擇: 5
   ```

2. **定期執行清理**

   ```bash
   # 每月執行一次
   python session_data_manager_tool.py
   # 選擇: 3 預覽
   # 選擇: 4 真實清理
   ```

3. **監控驗證率**
   - 保持在 > 95%
   - 定期檢查待驗證項

4. **備份重要數據**
   - cleanup 前備份
   - 保留歷史記錄

### ❌ 避免做法

1. 不要手動刪除系統文件
2. 不要修改 tracked.json 文件
3. 不要跳過驗證步驟
4. 不要同時運行多個清理任務

## 🆘 故障排除

### 問題1：驗證率低於95%

**原因**：

- 最近很多新會話未驗證（正常）
- 某些會話記錄損壞

**解決**：

- 等待10分鐘後自動驗證
- 檢查會話記錄完整性
- 查看驗證報告找出問題會話

### 問題2：清理建議中沒有廢棄文件

**原因**：

- 系統整潔，沒有廢棄文件
- 文件被認為是重要數據而被保護

**解決**：

- ✅ 這是正常的，說明系統維護良好
- 檢查 protected_files 列表

### 問題3：清理失敗

**原因**：

- 權限不足
- 文件被佔用
- 路徑不存在

**解決**：

- 用 `sudo` 提升權限
- 關閉使用該文件的程序
- 檢查文件路徑

## 🎉 總結

會話數據管理系統提供了：

✅ **全自動記錄** - 對話自動保存到系統
✅ **定期驗證** - 10分鐘自動驗證記錄
✅ **智能清理** - 識別並清理廢棄數據
✅ **結構保護** - 保持文件夾組織層次
✅ **安全機制** - 雙重確認，保護重要文件

這是一個完整的**對話記錄 → 驗證 → 清理**的自動化系統，確保你的數據始終是最新的、完整的、整潔的！

---

**版本**: 1.0.0
**狀態**: ✅ 生產就緒
**最後更新**: 2026-02-28

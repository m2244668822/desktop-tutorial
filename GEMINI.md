# Project Instructions: AI Agent System with Unified Memory

## 核心架構規範 (Core Architecture)

1. **記憶系統 (Memory System)**:
    - 必須維持「三層記憶」機制：短期(Context)、中期(Summary)、長期(Knowledge Hub)。
    - **GPT 紀錄庫整合**: `chat_history.db` 是長期記憶的法定來源之一，必須確保 `core/memory_layers.py` 持續支援從此資料庫提取對話。
    - **知識中樞 (Knowledge Hub)**: 所有對話與本地知識必須透過 `KnowledgeHub` 進行索引與檢索。

2. **自動化與背景服務 (Automation)**:
    - **GPT History Server**: 為提供即時紀錄查詢，`.tmp_chatgpt_server.py` 應視為核心服務，隨主系統啟動。
    - **自適應巡檢**: 智能體必須在每輪對話前取得「系統主動巡查快照」(System Inspection Snapshot)，以保持對硬體負載與 Git 狀態的感知。

3. **開發規範 (Development Standards)**:
    - 任何對記憶層的修改不得導致 `chat_history.db` 斷連。
    - 必須維持對 Windows 環境 (cp950) 的編碼相容性，所有 `print` 輸出需經由 `_safe_print` 或類似機制處理。

## 永久運行維護 (Maintenance)

- 定期執行 `KnowledgeHub.rebuild()` 以吸收新的對話紀錄。
- 確保 `.venv` 環境包含 `numpy`, `faiss-cpu`, `sqlite3` 等核心依賴。

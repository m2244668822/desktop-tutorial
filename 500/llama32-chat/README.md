# 🚀 llama32-chat 核心系統

這是智能體協作工作區的核心中樞，負責神經網路、自主學習與對話引擎。

---

## 🏗️ 核心架構 (Core Architecture)

- **`core/`**: 系統心臟。包含中樞神經 (`autonomous_agent.py`) 與統一學習中樞 (`unified_learning_hub.py`)。
- **`learning/`**: 系統大腦。負責 RAG 檢索、自適應神經成長與知識蒸餾。
- **`agents/`**: 專業智能體。處理代碼更新、任務管理與流量控制。

---

## 📂 文檔導覽 (Documentation)

詳細文檔已移至 `docs/` 目錄：

- **[📚 文檔索引](docs/00_文檔索引.md)** - 導航至 01-09 模塊化指南。
- **[🧠 神經系統指南](docs/NEURAL_SYSTEM_COMPLETE_GUIDE.md)** - 深入了解自主學習機制。
- **[🇨🇳 中文說明](docs/zh/)** - 系統功能與架構的詳細中文解說。

---

## 🛠️ 管理工具 (Tools)

您可以通過以下路徑訪問專用工具：

- **監控**: `python3 tools/monitor.py`
- **系統指南**: `python3 tools/system_guide.py`

---

## 📊 數據與日誌 (Data & Logs)

- **配置**: `config/autonomous_config.json`
- **對話數據**: `data/conversations.json`
- **系統診斷**: `data/diagnostics/`

---

_核心系統版本: 2.0 (Gemini Integrated)_

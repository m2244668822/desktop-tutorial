# 🤖 智能體協作工作區 (Gemini + Local Memory)

> **當前狀態**: 🚀 系統已升級至 Gemini 2.0 Flash 並完成 13 個記憶源整合。  
> **最後維護**: 2026-04-28

---

## ⚡ 快速啟動 (Quick Start)

系統已整併為單一主入口：

1. **Web 主模式（推薦）**

   ```bash
   ./start_desktop_chat_app.sh web --open-browser
   ```

2. **桌面模式（pywebview）**

   ```bash
   ./start_desktop_chat_app.sh desktop
   ```

3. **健康檢查**

   ```bash
   ./start_desktop_chat_app.sh health
   ```

---

## 📚 文檔地圖 (Documentation Map)

為了保持工作區整潔，詳細文檔已整合存放：

### 🛠️ 核心指南 (Guides)

- [🚀 系統設置與啟動](docs/SYSTEM_SETUP_AND_LAUNCH.md) - **最推薦！** API 設置、環境變數與啟動模式。
- [🏗️ 架構與目錄地圖](docs/SYSTEM_ARCHITECTURE_MAP.md) -
  深入了解工作區結構與 `500/llama32-chat` 組件。
- [🧭 Data Layer SOT](docs/DATA_LAYER_SOURCE_OF_TRUTH.md) - 資料層權威來源、路徑分工、每日檢查指令。
- [自適應神經系統](docs/自適應神經成長系統指南.md) - 了解系統如何從對話中學習。

### 📊 系統報告 (Reports)

- [中期改進總結](reports/中期改進實施報告.md) - 關於分頁 API 與搜索擴展的改進說明。
- [數據庫問題診斷](reports/完整數據庫問題報告.md) - 歷史數據加載問題的修復記錄。
- [最新觀測報告](reports/observability/latest.md) - 系統運行狀態與性能監控。

### 🔧 工具說明 (Tools)

- [本地記憶 API](docs/本地記憶API使用指南.md) - 如何調用本地 10,000+ 條對話記憶。
- [桌面端優化](docs/DESKTOP_CHAT_OPTIMIZATION_GUIDE.md) - 提升桌面聊天軟體穩定性的方法。

### 🔐 Git 協作規範 (Git Workflow)

- [PR 模板（GitHub）](.github/pull_request_template.md) - 每次合併前填寫 Busy 保護、驗證與回滾方案。
- [Branch Protection 清單](docs/dev/GITHUB_BRANCH_PROTECTION_CHECKLIST.md) - `main` 分支保護建議設定。
- [Git 自動化 + Skill 指南](docs/dev/GIT_AUTONOMY_SKILL_GUIDE.md) - 依變更範圍套用對應 skill 與流程。

---

## 📂 目錄結構速覽

```text
/
├── system_main.py              # 單一主程式入口（統一模式切換）
├── start_desktop_chat_app.sh   # 啟動腳本（web/desktop/health）
├── desktop_chat_app.py         # 主應用程式（前後端橋接）
├── docs/                       # 📚 所有技術指南與使用說明
├── tools/                      # 🔧 核心工具腳本 (API, 管理器)
├── reports/                    # 📊 系統診斷與改進報告
├── config/                     # ⚙️ 配置文件 (API Keys, 提示詞)
└── 500/llama32-chat/           # 🚀 核心神經網路系統代碼
```

---

## 🧠 下一階段架構升級（Control System）

一句話目標：  
把現在的「工具集合」升級成「有結構的控制系統」。

### 1) Command Layer（關鍵）

把呼叫路徑統一為：  
`UI -> Command -> API`

統一命令格式：

```json
{
  "command": "chat | sync | status",
  "payload": {},
  "meta": {
    "async": true
  }
}
```

好處：

- 前後端解耦，UI 不直接耦合底層 API。
- 同一協議可擴展多 Agent 與多後端。
- 更容易做權限控管與審計。

### 2) Sync 升級為可觀測任務流

目前只有 job status，建議升級為 step-based 流程：

```json
{
  "job_id": "sync-20260429-001",
  "steps": [
    {"name": "fetch_data", "status": "done"},
    {"name": "process", "status": "running"}
  ]
}
```

好處：

- 從黑盒變成透明流程。
- 故障定位更快（可直接看卡在哪一步）。
- 可支援中斷恢復與重試策略。

### 3) UI 分層（強烈建議）

建議 UI 結構拆成三層：

- `Chat Layer`：對話互動。
- `Control Layer`：sync/trigger/command 控制。
- `Observability Layer`：logs/latency/trace/job steps。

好處：

- 降低聊天與控制訊號互相干擾。
- 使用者心智模型更清楚。
- 維護與迭代效率更高。

### 4) Token 機制優化

引入 `dev/prod` 模式：

- `dev mode`：本地自動注入 token（提升開發效率）。
- `prod mode`：嚴格驗證 token（避免未授權請求）。

好處：

- 避免開發階段頻繁卡在 403/503。
- 上線時保持安全邊界。

### 5) Agent State（讓 Agent 持續化）

從 stateless chat 升級為有狀態的 Agent：

```json
{
  "agent_state": {
    "mode": "analysis | execution",
    "memory": [],
    "active_job": ""
  }
}
```

好處：

- 任務上下文可延續，不必每輪重建。
- 可以做 job-aware 行為（知道自己正在跑什麼）。
- 更適合多步驟任務與長流程。

### 6) 驗證方法（必測）

- `sync` 中斷後能否恢復。
- `chat + sync` 同時操作是否產生競態或混亂。
- latency/trace panel 是否能有效協助 debug。

### 7) 核心升級方向（濃縮）

- API 呼叫 Command 化。
- Sync 流程可觀測化。
- UI 以 Chat/Control/Observability 分層。
- Agent 狀態持續化。

---

## 🆘 故障排除

- **API Key 報錯**: 請確認 provider 官方網站申請的金鑰已存入 macOS Keychain 或 Windows Credential Manager；不要放入聊天或 `.env`。
- **記憶無法加載**: 執行 `python3 diagnose_memory.py` 進行檢查。
- **啟動緩慢**: 嘗試 `python3 start_lightweight_chat.sh` 使用輕量化模式。

---

由 Gemini CLI 智能體整理優化。

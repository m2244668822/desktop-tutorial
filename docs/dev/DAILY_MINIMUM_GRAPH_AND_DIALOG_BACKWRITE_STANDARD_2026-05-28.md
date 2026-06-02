# 每日最低標準：關係圖與對話回寫 - 2026-05-28

## 目的
這份文件把「關係圖要長得像神經元，不要亂長線」落成每日操作規則。它是新增筆記、對話回寫、文件整併與申言者->工程師協作的共同標準。

## 必連三條線
每一份新產出的筆記，至少要包含 3 條功能性連結：

1. 連到中樞 MOC：架構、運維或訓練三主幹之一。
2. 連到技術政策：例如單一入口、Mac/Windows 共用工作區或啟動編碼交接。
3. 連到任務/報告：具體進度、驗證或審計報告。

## 三主幹重力中心
| 主幹 | Obsidian 節點 | 負責內容 |
|---|---|---|
| 架構 | [[05_MOC_架構群組_2026-05-26]] | 系統拓撲、API 契約、前後端路由、單一入口 |
| 運維 | [[06_MOC_運維群組_2026-05-26]] | 啟動、Git、n8n、端口、環境維護、救援流程 |
| 訓練 | [[07_MOC_訓練群組_2026-05-26]] | 學習、記憶、RAG、FAISS/SQLite、回覆優化 |

乾淨入口固定為：[[12_基礎啟動與文件治理交接_2026-05-27]]。

## 技術政策必選
- [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]
- [[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]
- [[ProjectDocs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27]]

## 任務/報告必選
- [[ProjectDocs/dev/ARCHITECTURE_BASELINE_AND_MD_BUNDLE_AUDIT_2026-05-27]]
- [[ProjectDocs/dev/MD_BUNDLE_INDEX_2026-05-27]]
- [[ProjectDocs/dev/MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26]]

## 檔名與碎裂化規則
- 禁止新建 `未命名.md`。
- 標題必須包含「主題 + 日期」。
- 同主題筆記要共用一組關鍵詞，例如 `single-entry`, `ops-startup`, `dialog-backwrite`, `training-overlay`。
- 舊 `docs/`、`reports/`、`500/llama32-chat/docs/` 是歷史箱子：先貼標籤再抽取，不隨機亂連。

## 神經連結標籤二次判讀
只有符合以下至少一項，才建立強連結：

- 可執行規則：能改變實際流程或程式行為。
- 可驗證命令：能用測試、健康檢查或 Git 狀態驗證。
- 提升穩定性：能讓回覆、啟動、同步、記憶更穩。

若只是語意相近但沒有流程關係，先放入 [[10_待判定收件匣_2026-05-26]]。

## 申言者與工程師協作規則
- 申言者原本能力保留：風險分級、價值衝突判讀、帽子安全交接。
- 工程語譯是附加能力，不覆蓋原本能力。
- 使用者提出想法時，申言者可以把它翻譯成工程師可執行約束。
- 工程師負責實際修改程式、文件、測試與資料回寫。

## 對話回寫機制
系統每輪重要對話應回寫：

- `data/interaction_graph/turn_index.jsonl`：回合、角色、關鍵字、摘要。
- `data/interaction_graph/edges.jsonl`：關鍵字、檔案、MOC、報告之間的邊。
- `data/interaction_graph/engineer_handoffs.jsonl`：申言者轉工程師的工程語譯。

## 自適應神經成長階段
| 階段 | 數據量 | 連結強度 |
|---|---:|---:|
| 初生期 | 0+ | 1.0x |
| 成長期 | 1000+ | 1.2x |
| 穩定期 | 高頻被引用節點 | 依使用頻率強化，但仍需二次判讀 |

## 今日驗收
1. 新增筆記至少 3 條功能性連結。
2. 新筆記不使用未命名。
3. 申言者->工程師 handoff 寫入 JSONL。
4. 前端對話仍可走真 LLM，模板只做 fallback。
5. Git 修改前後都保留未提交資料，不覆蓋快照。

## 2026-05-28 穩定化補強
本日新增穩定化報告：[[ProjectDocs/dev/N8N_AND_PROPHET_ENGINEER_STABILITY_REPORT_2026-05-28]]。

- n8n 若像卡住，先看是否為資料過大；目前 `.n8n` 最大 WAL 約 3.94 MB，主因不是資料量，而是遙測 DNS 與 watchdog 等待時間太短。
- n8n 仍必須走獨立 Windows `cmd.exe` 通道，不能混進主 Web 啟動腳本。
- 申言者->工程師交接單必須使用固定可靠格式，不讓雲端 LLM 自由產生不存在的程式碼。
- FAISS 採「原始語言資料 + 繁體中文生活化理解層」：SQLite 保存可讀文字，FAISS 保存向量索引，AEG 保存關鍵字關係。
## 智能體長期記憶與 AEG 搜尋確認
目前系統採用「共用搜尋層、依角色分流記憶」：

- 每個角色都可透過 `KnowledgeHub` 搜尋長期資料。
- 對話永久記憶以 `agent_name` / role 分流保存，不是各自孤立資料庫。
- AEG 關聯圖位於 `data/knowledge_hub/aeg_keyword_graph.json`，供總管、研究員、工程師、小編、申言者等角色共用。
- 前端與 API 可透過 `/api/diag` 的 `agent_memory_aeg` 欄位確認狀態。

### 驗證欄位
| 欄位 | 意義 |
|---|---|
| `long_term_memory` | 角色可寫入/讀取長期記憶層 |
| `knowledge_search` | 角色可走 KnowledgeHub 搜尋 |
| `aeg_search` | 角色可讀 AEG 關鍵字關聯圖 |
| `shared_memory_layer` | 使用共同記憶層，依角色分流 |
| `shared_knowledge_hub` | 使用共同 KnowledgeHub，不建立孤島 |

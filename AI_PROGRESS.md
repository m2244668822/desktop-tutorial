# AI Progress Log

> 用途：只記錄會實際影響 AI 系統方向、架構優先級、里程碑或能力判定的事項。
> 原則：區分「已確認」「待驗證」「已退役」，避免把概念、計畫或舊程式誤寫成現況。

## 2026-07-26 基準

### 已確認

- 目前真正的最新程式主要仍在本機，尚未完整 commit / push 到 GitHub。
- GitHub `main` 目前只能視為舊展示／舊基準版本，不能單獨代表最新實際運作狀態。
- 現行主線是：
  1. 前端 AI 對話系統
  2. NotebookLM／研究資料整合
  3. Agent／模型路由
  4. 歷史對話、研究資料與橋接資料的串聯
  5. 改善多輪對話狀態與任務續接
- 影片剪輯／Seedance 已退出目前產品主線。舊 GitHub 內若仍有 `VIDEO_*`、`SEEDANCE_*`、影片 route 或設定，視為 legacy code。
- 目前前端已觀察到重要互動問題：AI 先列出 1～4 選項，使用者回答後，系統可能重新分流並再次澄清，形成 ask-back loop。

### 目前最高優先級

#### P0 Conversation State Machine

需要讓系統先判斷：

- 使用者這一句是否在回答上一輪問題
- 是否存在 pending action / pending question
- 哪個 Agent 擁有目前 workflow
- 是否應續接原流程，而不是重新進入全域 Router

建議優先順序：

```text
User Input
  ↓
Conversation State / Pending Action
  ├─ 有未完成流程 → Resume 原 workflow / 原 Agent
  └─ 無未完成流程 → Router
                         ↓
                    Agent / Model
                         ↓
                 Research / NotebookLM
                         ↓
                 Response + State Save
```

核心原則：

> 能用既有狀態確定的事情，不重新交給 LLM 猜；能續接上一輪的任務，不重新啟動全域分流。

### P1 Workflow Ownership

建議至少維護：

- `session_id`
- `active_agent`
- `active_workflow`
- `state`
- `pending_question`
- `pending_options`
- `clarification_count`

### P2 Deterministic Routing

以下輸入應優先用規則解析，而不是先交給 LLM：

- `1` / `2` / `3` / `4`
- 「第二個」
- 「就這個」
- 「可以」
- 「取消」
- 明確指令與按鈕事件

### P3 Research / NotebookLM Integration

目前產品方向應逐步形成：

```text
Frontend
  ↓
Conversation State
  ↓
Agent / Model Router
  ↓
NotebookLM / Research Data
  ↓
Memory / Database / Bridge
  ↓
Response
```

### P4 Multi-Agent Compare-and-Fuse

`IN_PROGRESS / HYPOTHESIS`：使用者明確指定未來智能體不只分工，而要能互相比較、批判、挑選較佳部分，再融合成一個更好的輸出。

目標不是讓多個 Agent 同時講話，而是形成可驗證的集體決策流程：

```text
Task
  ↓
Independent Drafts
  ├─ Agent A
  ├─ Agent B
  └─ Agent C
  ↓
Comparison / Critique
  ├─ 正確性
  ├─ 證據
  ├─ 完整度
  ├─ 可執行性
  └─ 風險
  ↓
Selection
  ↓
Fusion / Synthesis
  ↓
Verifier
  ↓
Final Answer
```

建議拆成四個元件：

1. `candidate_generation`：各 Agent 先獨立產生候選答案，避免一開始互相污染。
2. `peer_review`：Agent 彼此指出優點、缺點、衝突與遺漏。
3. `fusion`：不是投票選一個，而是抽取各候選的最佳部分重新組合。
4. `verifier`：最後檢查事實、邏輯、格式、任務完成度與安全邊界。

重要限制：

- Agent 數量增加不等於答案一定更好。
- 比較標準必須依任務而變，不可所有任務只用單一分數。
- 最終融合結果必須保留 `source_agent`、`reason`、`confidence` 或等價 trace，避免無法回查為什麼採用某一部分。
- 在 Conversation State 尚未穩定前，不應讓 Compare-and-Fuse 搶走 P0 優先級，否則只是把更多 Agent 放進同一個循環。

預計成熟度門檻：

- M0：已有 Compare-and-Fuse 架構定義。
- M1：至少兩個 Agent 可獨立產生候選並送入比較器。
- M2：系統可自動輸出融合結果。
- M3：多輪任務中不會因比較流程破壞 workflow state。
- M4：有 benchmark / trace 證明融合後平均優於單一 Agent baseline。
- M5：前端可穩定選擇「單 Agent / 多 Agent 協作」模式並對一般使用者透明運作。

## 2026-07-27 開源 Agent 架構基準

### HYPOTHESIS / ARCHITECTURE BASELINE

此區不是宣告目前程式已完成，而是作為之後校正本機最新版的開源工程基準。

建議參考棧：

1. **AutoGen / Graph-style orchestration**
   - 用途：校正多智能體的分工、流程、條件分支、平行執行、停止條件與 group chat / workflow orchestration。
   - 對本專案的主要價值：避免 Agent 無限互問、重複分流與無終止條件的循環。

2. **A2A-style Agent Interface**
   - 用途：校正 Agent 之間的能力描述、輸入輸出契約、任務交換與 handoff。
   - 每個固定 Agent 未來應逐步具備：`identity`、`capabilities`、`input_schema`、`output_schema`、`tools`、`permissions`、`handoff_rules`。

3. **MCP-style Tool / Knowledge Interface**
   - 用途：把工具、資料源、研究資料與外部能力從 Agent 本身解耦，避免每個 Agent 各自硬接 API。
   - 對本專案的主要價值：NotebookLM／研究資料、資料庫與其他工具可以成為一致的可呼叫資源層。

4. **Handoff + Termination**
   - 用途：Agent 不適合繼續處理時，明確交棒；流程達成條件後必須可停止。
   - 核心原則：handoff 是續接原 workflow，不是把使用者輸入重新送回全域 Router。

5. **Guardrails / Boundary Keeper**
   - 用途：把「守門員」從人格提示升級成輸入、輸出、工具與權限層的程式機制。
   - 建議能力：`input_validation`、`tool_permission`、`output_validation`、`evidence_check`、`stop_or_reject`。

6. **Tracing / Evaluation**
   - 用途：每次 Agent、tool、handoff、fusion、verifier 都留下可追蹤事件。
   - 建議至少保留：`trace_id`、`session_id`、`source_agent`、`target_agent`、`reason`、`tool`、`result`、`confidence`、`error`。

7. **Compare-and-Fuse**
   - 與現有 P4 整合：Candidate → Critic → Evidence Check → Fusion → Verifier。
   - 評估時應盲化候選來源，避免因 Agent 名稱產生角色偏誤。
   - 必須用 benchmark 驗證融合結果是否平均優於單一 Agent baseline。

### 建議新的工程優先序

```text
P0 Conversation State
↓
P1 Workflow Ownership
↓
P2 Deterministic Routing
↓
P3 NotebookLM / Knowledge Integration
↓
P4 Handoff + Termination
↓
P5 Compare-and-Fuse
↓
P6 Guardrails / Permission
↓
P7 Tracing / Evaluation / Benchmark
```

### 固定 Agent 的校正原則

目前已有的固定角色不需要因採用開源框架而推翻。開源框架只負責校正「如何協作」，角色本身仍保留本專案的定位。

例如：

```text
Researcher → 研究判斷
Reader → 證據與資料支持檢查
Questioner → 漏洞／反例／假設檢查
Engineer → 技術與可實作性
Proclaimer / Coordinator → 協調、收束與 workflow ownership
Scribe → 記錄、trace、知識沉澱
Boundary Keeper → guardrail / permission / stop
Editor / Xiaobian → 表達、產品化與介面輸出
```

核心原則：

> 單一 Agent 可以可靠完成的任務，不強制啟動多 Agent；多 Agent 的存在必須帶來可驗證的品質提升，而不是只增加流程與 token。

## 待驗證

- NotebookLM 整合目前實際完成到哪個層級：資料匯入、查詢、前端 UI、Agent 調用、引用回傳、同步等，需以尚未上傳的本機最新版程式為準。
- 本機最新版是否已完全移除所有影片相關 route / config / dependencies，需等本機版本 commit / push 後重新掃描。
- 對話循環問題的真正觸發函式與狀態遺失位置，需分析本機最新版程式才能定位。
- Compare-and-Fuse 是否已存在任何本機實作、評分器、review agent、融合器或 verifier，需等本機最新版上傳後確認。
- 本機最新版是否已有 MCP / A2A / handoff / guardrail / tracing 類似實作，需在上傳後逐項比對，而不是只看命名。

## 已退役

- 影片剪輯工作流
- Seedance 作為目前主產品方向

## 2026-07-27 進度追蹤機制

### CONFIRMED — 建立 AI 里程碑門檻

之後不只記「做了什麼」，而是把每個重要能力標到以下成熟度：

```text
M0 IDEA        想法／方向
M1 WIRED       程式已接線，可以被呼叫
M2 WORKING     實際操作可完成主要任務
M3 STABLE      多輪使用不容易失去狀態或循環
M4 VERIFIED    有測試、log、引用或可重現驗證
M5 PRODUCT     可由一般使用者在前端穩定使用
```

### 目前暫定成熟度（以可確認資訊為限）

| 模組 | 暫定級別 | 狀態 | 說明 |
|---|---:|---|---|
| 前端 AI 對話 | M2 | CONFIRMED | 已可實際互動，但存在多輪 ask-back loop。 |
| Agent / Model Router | M2 | CONFIRMED | 舊 GitHub 已有路由與 Agent 規格；最新版仍待本機程式驗證。 |
| Conversation State | M0-M1 | BLOCKER | 已確認需要，但目前無法從 GitHub 證明已完整接入。 |
| NotebookLM / Research Integration | M1? | IN_PROGRESS | 使用者確認為目前主線，但實際完成程度必須等本機最新版上傳後判定。 |
| Multi-Agent Compare-and-Fuse | M0 | IN_PROGRESS / HYPOTHESIS | 已明確定義為核心能力；尚未從 GitHub 證明有可運作實作。 |
| Memory / DB / Bridge | M2 | CONFIRMED | 舊版已有 SQLite/PostgreSQL、ChatGPT Bridge / ingest / sync 基礎。 |
| Agent Governance / Permission / Verifier | M0 | HYPOTHESIS | 有長期價值，但目前優先級低於 Conversation State 與 NotebookLM 主線。 |
| Open-source Architecture Alignment | M0 | HYPOTHESIS | 已建立 AutoGen/A2A/MCP/Handoff/Guardrail/Tracing 對照基準，待本機新版上傳後逐項驗證。 |
| Video / Seedance | — | RETIRED | 不再計入現行 AI 產品進度。 |

> `M1?` 表示方向已由使用者確認正在實作，但目前 GitHub 沒有足夠新版程式證據，因此不得當成完成事實。

### 下一個有效里程碑

**Milestone A：本機最新版進入 Git / GitHub 後，完成一次「真實架構盤點」。**

盤點至少要回答：

1. NotebookLM 已接到哪一層：UI、後端、Agent、資料同步、引用回傳。
2. Conversation State 是否已存在持久化或 session-level state。
3. `1 / 2 / 3 / 4` 等回答是否會優先續接 pending workflow。
4. Compare-and-Fuse 是否已有 candidate / review / fusion / verifier 任一實作。
5. 是否已有 handoff / termination 機制，且不會重新觸發全域 Router。
6. 是否已有 MCP/A2A 類似的工具與 Agent 介面層。
7. 是否已有 guardrail / permission / tracing / evaluation。
8. 哪些 legacy video / Seedance 程式已真正移除。
9. 前端實際資料流是否為：`User → State → Router → Research/NotebookLM → Memory → Response`。

完成後，才更新各模組 M0～M5 等級。

## 之後新增進度時的標記規則

每一筆新資訊至少標示一種：

- `CONFIRMED`：已從程式、commit、測試或實際操作確認
- `IN_PROGRESS`：正在開發，但尚未完成驗證
- `HYPOTHESIS`：架構推測或值得測試的方向
- `BLOCKER`：會阻礙目前主線的問題
- `RETIRED`：已停止，不再作為現行方向

只有真正改變 AI 系統進度判斷的資訊才寫入本檔，避免把一般新聞或靈感塞成進度。
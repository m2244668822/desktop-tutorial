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

## 待驗證

- NotebookLM 整合目前實際完成到哪個層級：資料匯入、查詢、前端 UI、Agent 調用、引用回傳、同步等，需以尚未上傳的本機最新版程式為準。
- 本機最新版是否已完全移除所有影片相關 route / config / dependencies，需等本機版本 commit / push 後重新掃描。
- 對話循環問題的真正觸發函式與狀態遺失位置，需分析本機最新版程式才能定位。

## 已退役

- 影片剪輯工作流
- Seedance 作為目前主產品方向

## 之後新增進度時的標記規則

每一筆新資訊至少標示一種：

- `CONFIRMED`：已從程式、commit、測試或實際操作確認
- `IN_PROGRESS`：正在開發，但尚未完成驗證
- `HYPOTHESIS`：架構推測或值得測試的方向
- `BLOCKER`：會阻礙目前主線的問題
- `RETIRED`：已停止，不再作為現行方向

只有真正改變 AI 系統進度判斷的資訊才寫入本檔，避免把一般新聞或靈感塞成進度。

<!-- markdownlint-configure-file
{
  "MD013": {
    "line_length": 120,
    "tables": false
  },
  "MD060": {
    "style": "compact"
  }
}
-->

# 智能體協作修復會後總結

- 產生時間：2026-06-06T16:32:59
- 工作區：`/Volumes/智能體/城城城程式`
- 審計事件數：24
- 總分數變化：-67

## 任務目標

讓 Perob 入口、OpenClaw 接管、DesktopBridge 回退與智能體學習標記形成可追蹤閉環。

## 實際路由

- 優先路由：Perob API -> OpenClaw Gateway
- 補救路由：OpenClaw 失敗 -> DesktopBridge
- 外圍協調：n8n 維持 optional，不阻斷核心對話

## 錯誤選擇與補救結果

| 時間 | 智能體 | 規則 | 分工 | 路由 | 選擇 | 結果 | 補救 | 分數 |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |
| 2026-06-06T00:56:56 | 工程師 | — | — | openclaw_websocket | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T01:09:57 | 工程師 | — | — | openclaw_websocket | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T01:14:27 | 工程師 | — | — | openclaw_websocket | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T01:18:15 | 工程師 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T01:22:36 | 工程師 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T01:26:43 | 工程師 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T13:45:33 | 總管中樞 | ENTRY_CHECK_ORDER、OPENCLAW_FALLBACK_REQUIRED、N8N_OPTIONAL_ONLY、AUDIT_EVERY_REPAIR、PYTHON_RUNTIME_RISK | 工程師、帽子、申言者、總管中樞、研究員 | training_overlay | 將下次避免重犯規則轉成審計與資料層訓練任務 | training_required | 建立規則清單、分工與報告欄位，避免只留 console 或口頭提醒 | -10 |
| 2026-06-06T13:45:34 | 總管中樞 | ENTRY_CHECK_ORDER、OPENCLAW_FALLBACK_REQUIRED、N8N_OPTIONAL_ONLY、AUDIT_EVERY_REPAIR、PYTHON_RUNTIME_RISK | 工程師、帽子、申言者、總管中樞、研究員 | training_overlay | 完成審計欄位與報告產生器補強 | success | 測試已覆蓋規則清單、分工、學習標籤與下一道護欄 | +2 |
| 2026-06-06T15:33:10 | 研究員 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:34:00 | 研究員 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:35:15 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:36:06 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:38:38 | 研究員 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:39:07 | 研究員 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:39:07 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:42:46 | 帽子 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:43:44 | 帽子 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:44:31 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:45:20 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:46:23 | 帽子 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:47:23 | 帽子 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:48:14 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T15:48:14 | 申言者 | — | — | openclaw | OpenClaw 優先轉送 | failed | 回退 DesktopBridge | -3 |
| 2026-06-06T16:32:52 | 工程師 | ENTRY_CHECK_ORDER、OPENCLAW_FALLBACK_REQUIRED、AUDIT_EVERY_REPAIR、PYTHON_RUNTIME_RISK | 工程師、申言者、帽子、研究員、總管中樞 | desktopbridge_repair | 先用回歸測試重現三個衝突點，再修巡查快照、申言者記憶命中規則與前端錯誤分類。 | success | Git 巡查改為真實 git status；高分記憶必須有主題重疊才列為直接命中；前端 abort 改為 E_CLIENT_ABORT 並延長等待時間。 | +4 |

## 資料層訓練 Overlay

| 智能體 | 學習動作 | 訓練標籤 | 下一道護欄 |
| --- | --- | --- | --- |
| 總管中樞 | 資料層訓練，不覆蓋原本智能體對話模式；把規則融入審計與報告 | avoid_repeat_rules、agent_task_assignment、audit_learning、aeg_rag_overlay | 入口先測 5001 -> 5443 -> 前端；OpenClaw 無可讀回覆必須回退 DesktopBridge；n8n 不得阻斷核心對話。 |
| 總管中樞 | 將扣分事件轉為可追蹤訓練資料，供 AEG/RAG 與後續智能體檢索 | training_summary_generated、regression_guardrail、traditional_chinese_report | 每次類似任務完成後都重新生成會後總結，確認規則與分數有被記錄。 |
| 工程師 | 將錯誤案例寫成資料層訓練 overlay，避免巡查假訊號與無關記憶再次誤導智能體。 | agent_collaboration_conflict、git_snapshot、memory_relevance、frontend_abort、low_confidence_routing | 巡查快照不得使用 Mock；高分記憶需主題重疊；前端 abort 必須標記為等待/中止而非服務壞掉。 |

## 智能體個別心得

### 工程師

- 事件數：7
- 成功：1，需補救：6
- 分數：-14
- 心得：下次先確認路由可用性，再決定接管或回退；失敗不可卡住，必須留下補救紀錄。

### 帽子

- 事件數：4
- 成功：0，需補救：4
- 分數：-12
- 心得：下次先確認路由可用性，再決定接管或回退；失敗不可卡住，必須留下補救紀錄。

### 申言者

- 事件數：7
- 成功：0，需補救：7
- 分數：-21
- 心得：下次先確認路由可用性，再決定接管或回退；失敗不可卡住，必須留下補救紀錄。

### 研究員

- 事件數：4
- 成功：0，需補救：4
- 分數：-12
- 心得：下次先確認路由可用性，再決定接管或回退；失敗不可卡住，必須留下補救紀錄。

### 總管中樞

- 事件數：2
- 成功：1，需補救：1
- 分數：-8
- 心得：下次先確認路由可用性，再決定接管或回退；失敗不可卡住，必須留下補救紀錄。

## 下次避免重犯規則

1. `ENTRY_CHECK_ORDER`（負責：工程師）：入口問題先測 5001，再測 5443，最後才查前端。
2. `OPENCLAW_FALLBACK_REQUIRED`（負責：工程師）：OpenClaw 只要沒有可讀回覆，就必須回退 DesktopBridge。
3. `N8N_OPTIONAL_ONLY`（負責：總管中樞）：n8n 是 optional，不能因為排程器沒開就讓前端對話失敗。
4. `AUDIT_EVERY_REPAIR`（負責：總管中樞）：每次智能體做錯選擇或補救，都要寫入審計事件，不可只留在 console。
5. `PYTHON_RUNTIME_RISK`（負責：工程師）：Python 3.14 的 Pydantic v1 warning 要視為中期風險，主 runtime 優先固定在 3.11/3.12。

## 智能體任務分配

- 工程師：負責入口檢查順序、proxy、後端、OpenClaw fallback、Python runtime 風險。
- 帽子：負責 OpenClaw token、控制平面、Lobster approval checkpoint 與沙盒安全推演。
- 申言者：負責第一層危險等級分類，不能卡住任務，需轉交帽子或工程師。
- 總管中樞：負責任務分流、審計寫入、扣分加分、報告生成。
- 研究員：負責把錯誤案例轉成 AEG/RAG 弱關聯記憶，避免低信心鬼打牆。

## 結果摘要

- outcome 統計：{'failed': 21, 'training_required': 1, 'success': 2}
- 審計來源：`logs/agent_collaboration_audit.jsonl`

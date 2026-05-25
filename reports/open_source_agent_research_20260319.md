# 開源智能體研究摘要（2026-03-19）

## 目標

- 針對目前「總管回覆偏模板、工程執行鏈不夠實作化」問題，提供可落地的開源智能體能力來源。
- 支援三條線：研究員（資料）、工程師（優化）、中繼器（總管補強）。

## 研究員：可用開源框架（優先）

1. Microsoft Agent Framework

- 定位：企業級 workflow/orchestration。
- 適用：總管任務編排、可觀測性、策略治理。
- 來源：https://github.com/microsoft/agent-framework

2. LangGraph

- 定位：stateful graph agent。
- 適用：把「研究員 -> 工程師 -> 中繼器 -> 總管」流程做成可追蹤圖式工作流。
- 來源：https://github.com/langchain-ai/langgraph

3. OpenHands

- 定位：軟體工程代理與實作任務自動化。
- 適用：工程師線實際改檔、修復、驗證。
- 來源：https://github.com/All-Hands-AI/OpenHands

4. AutoGen

- 定位：多代理協作框架。
- 適用：角色式對話協作、任務分工訊息模式。
- 來源：https://github.com/microsoft/autogen

5. CrewAI

- 定位：角色導向 crew/task。
- 適用：快速建立「研究員/工程師/中繼器」協作模板。
- 來源：https://github.com/crewAIInc/crewAI

6. smolagents

- 定位：輕量 code agent。
- 適用：快速驗證新功能，不先投入重框架成本。
- 來源：https://github.com/huggingface/smolagents

## 工程師：可用評測資料

1. SWE-bench

- 用途：評估工程問題解決與修復能力。
- 來源：https://github.com/SWE-bench/SWE-bench

2. WebArena-Verified

- 用途：評估 web 任務代理與工具調度能力。
- 來源：https://github.com/ServiceNow/webarena-verified

## 中繼器：總管補強建議

1. 路由補強：固定總管作為入口，再分派角色流程。
2. 去重補強：同指令節流，避免狀態洗版。
3. 狀態補強：工作區摘要過濾噪音檔（如 `.DS_Store`）。
4. 彙整補強：每次任務後輸出「研究員 + 工程師 + 中繼器」整合報告。

## 本次已落地

- 已建立本地資料庫：`data/open_source_agent_catalog.json`
- 已在桌面總管新增可觸發三線回報與一鍵整合流程。

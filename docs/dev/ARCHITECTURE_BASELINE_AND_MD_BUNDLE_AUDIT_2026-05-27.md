# Architecture Baseline and MD Bundle Audit - 2026-05-27

## Executive Summary

Git has no fatal corruption. Runtime services are now healthy: 5001 is the single web/API entry, n8n is listening on 5678 with broker 5679, Ollama is on 11434, and SQLite/FAISS memory has 446 items. The remaining architecture problem is document governance: old docs, reports, and legacy 500 manuals need evidence-based linking before agents should treat them as active instructions.


## 快速交接入口
- `docs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27.md` 是 Windows/Mac 接手時的第一份啟動與編碼地圖。
- 它固定記錄主專案路徑、Obsidian Vault 路徑、UTF-8/ASCII 規則、Python 核心結構、端口與 Git 操作，避免每次重新偵測。

## Runtime Baseline

| Item | Result |
|---|---|
| Git fatal corruption | Not found |
| Empty git objects | 0 |
| `git fsck` note | dangling tree 3b21c11e539250c2254329a3c93b0bf2a60c1b32; dangling tree c521eae3bce69f78733dc0da2926caf57cfd3474 |
| Core pytest slice | 14 passed: route prefix, desktop web compatibility, frontend cleanup, command layer |
| KnowledgeHub | SQLite ready, FAISS ready, total_items=446 |
| n8n health | `/healthz` and `/healthz/readiness` return 200 |

### Ports

| Port | Role | Listening | PID |
|---:|---|---|---:|
| 5001 | single-entry web | True | 3996 |
| 5678 | n8n | True | 10228 |
| 5679 | n8n task broker | True | 10228 |
| 11434 | Ollama | True | 22484 |

## MD Bundle Summary

| Area | Count | Zero In | Zero Out | Outgoing Edges | Meaning |
|---|---:|---:|---:|---:|---|
| `P0-dev` | 13 | 2 | 5 | 37 | current spine |
| `archive` | 6 | 6 | 6 | 0 | history only |
| `docs` | 51 | 41 | 47 | 5 | old/current guides mixed |
| `legacy-500-docs` | 22 | 9 | 18 | 15 | legacy subsystem docs |
| `other` | 12 | 11 | 10 | 13 | supporting files |
| `reports` | 43 | 41 | 39 | 5 | snapshot reports |
| `skills` | 17 | 14 | 16 | 3 | supporting files |

## Required Actions by Need

| Need | Count | Action |
|---|---:|---|
| `CONSOLIDATE_OR_ARCHIVE` | 41 | Extract useful facts into P0 docs or Obsidian MOCs, then mark as historical snapshot. |
| `REVIEW_STALE_DOC` | 37 | Check against current code; update or merge into P0 docs. |
| `REVIEW` | 29 | Manual review. |
| `MERGE_IF_STILL_TRUE` | 22 | Compare with current 5001/LangGraph/Memory architecture before linking. |
| `REVIEW_ACTIVE_DOC` | 14 | Manual review. |
| `KEEP_CURRENT_CHECK_CODE_SYNC` | 9 | Keep as canonical, verify against code and tests. |
| `ARCHIVE_REFERENCE_ONLY` | 6 | Do not drive active decisions; cite only as history. |
| `REVIEW_P0_STALE` | 4 | Manual review. |
| `REVIEW_RECENT_REPORT` | 2 | Manual review. |

## Highest Priority Documents

- `docs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: gateway,n8n,cross-system
- `docs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: gateway,n8n,memory,cross-system
- `docs/dev/LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: gateway,cross-system
- `docs/dev/AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: gateway,n8n
- `docs/dev/CROSS_SYSTEM_LINKAGE_AND_DOC_CONSOLIDATION_2026-05-26.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: gateway,n8n,memory,cross-system,open-task
- `docs/dev/MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: gateway,n8n,open-task
- `docs/dev/GIT_STAGED_DATA_SLIMMING_AUDIT_2026-05-26.md` - KEEP_CURRENT_CHECK_CODE_SYNC - signals: langgraph
- `docs/DATA_LAYER_SOURCE_OF_TRUTH.md` - REVIEW_STALE_DOC - signals: memory
- `docs/DATA_TRACKING_TIERS.md` - REVIEW_STALE_DOC - signals: none

## Why Old Docs Must Not Be Hard-Deleted

- `reports/` contains execution snapshots. They are not the steering wheel, but they may contain evidence that explains why a fix was made.
- `docs/` mixes current guides and stale guides. Deleting by folder would destroy some useful source-of-truth fragments.
- `500/llama32-chat/docs/` is a legacy subsystem manual set. It should be treated like an old machine manual: compare to the current machine before reusing.

## Next Merge Policy

1. Link every active doc back to a P0 spine doc or one of the architecture/ops/training MOCs.
2. Reports stay snapshots unless a human extracts a fact into `docs/dev/` or Obsidian root MOC.
3. Legacy 500 docs require code verification before becoming active guidance.
4. Files with zero links are not automatically wrong; they are marked as untrusted until linked with evidence.

## Detailed Rows: docs / reports / legacy 500

| Path | Area | In | Out | Need | Signals | Heading |
|---|---|---:|---:|---|---|---|
| `docs/runbooks/cors-low-restrict-policy.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | CORS 與最低權限模式政策（永久記憶） |
| `docs/runbooks/frontend-backend-route-compat.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | gateway | 前後端路由相容 Runbook（永久記憶） |
| `docs/runbooks/knowledge_hub_faiss_enablement.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | memory | Knowledge Hub FAISS 啟用補強 Runbook |
| `docs/runbooks/startup-command-contract.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | gateway | 啟動命令契約（永久記憶） |
| `docs/履歷使用指南.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | 履歷使用指南 |
| `docs/快速參考.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | 📖 會話數據管理系統 - 快速參考指南 |
| `docs/智能體快速啟動.md` | `docs` | 0 | 1 | `REVIEW_ACTIVE_DOC` | - | 🚀 智能體快速啟動 |
| `docs/智能體快速啟動_英文版.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | 🎯 智能體快速啟動指南 |
| `docs/本地記憶API使用指南.md` | `docs` | 1 | 0 | `REVIEW_ACTIVE_DOC` | cross-system | 本地記憶 API 使用指南 |
| `docs/檔案清單總覽.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | 📋 會話數據管理系統 - 完整文件清單 |
| `docs/終端機快速操作_智能體控制台失靈救援.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | gateway | 終端機快速操作：智能體控制台失靈救援 |
| `docs/網狀語言比對_進度回報_2026-04-11.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | 網狀語言比對進度回報（2026-04-11） |
| `docs/聊天系統說明.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | AI 聊天工具使用指南 |
| `docs/自適應神經成長系統_README.md` | `docs` | 0 | 0 | `REVIEW_ACTIVE_DOC` | - | 🌱 自適應神經成長系統 |
| `docs/AGENT_SYSTEM_GUIDE.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 🧠 智能體統一系統 - 完整使用指南 |
| `docs/AGENT_UPGRADE_READY.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | memory | ✅ 升級完成總結 - 你的智能體已就緒運營 |
| `docs/DATA_LAYER_SOURCE_OF_TRUTH.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | memory | Data Layer Source of Truth |
| `docs/DATA_TRACKING_TIERS.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | Data Tracking Tiers |
| `docs/DESKTOP_CHAT_OPTIMIZATION_GUIDE.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | langgraph | 桌面聊天軟體優化指南 |
| `docs/GEMINI_SETUP_GUIDE.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | cross-system | 🚀 Gemini + 本地記憶統一對話系統 - 完整設置指南 |
| `docs/LEARNING_SESSION_PROGRESS.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 🧠 智能體持續自主學習進度報告 |
| `docs/MODEL_OPTIMIZATION_GUIDE.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | cross-system | 🖥️ 模型優化指南 - 8GB RAM Mac 配置 |
| `docs/README_SESSION_DATA_MANAGEMENT.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | n8n | 🗂️ 會話數據管理系統 - 完整指南 |
| `docs/README_UNIFIED_LEARNING.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 🧠 中枢神经统一学习系统 - 最优解决方案 |
| `docs/Remotasks商業運營系統完整交付.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 🎯 Remotasks 商業運營系統 - 完整交付 |
| `docs/Remotasks收益啟動指南.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | - | Remotasks 收益啟動指南 |
| `docs/Remotasks自動週報使用說明.md` | `docs` | 0 | 1 | `REVIEW_STALE_DOC` | cross-system | Remotasks 自動週報使用說明 |
| `docs/SYSTEM_ARCHITECTURE_MAP.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | memory | 🏗️ 工作區架構與目錄地圖 (Architecture Map) |
| `docs/SYSTEM_SETUP_AND_LAUNCH.md` | `docs` | 1 | 1 | `REVIEW_STALE_DOC` | - | 🚀 系統設置與啟動全攻略 (System Setup & Launch) |
| `docs/SYSTEM_VERIFICATION_REPORT.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | - | 🎯 會話數據管理系統 - 完整驗證報告 |
| `docs/UNIFIED_LEARNING_SUMMARY.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 🎯 统一学习系统 - 最优解实施总结 |
| `docs/WORKSPACE_ORGANIZATION_PLAN.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 📁 智能體工作區 - 完整分類方案 |
| `docs/WORKSPACE_ORGANIZATION_SUMMARY.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 🎉 智能體工作區整理 - 最終總結 |
| `docs/agent_v1/README.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | langgraph,memory | Agent V1 (3/6/7/8) 實作說明 |
| `docs/ooschool_live_sync_steps.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | gateway,cross-system | OOSchool 主動讀頁同步步驟 |
| `docs/中期改進_快速指南.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 中期改進快速使用指南 |
| `docs/優化摘要.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 文件系統學習優化總結 |
| `docs/學習系統說明.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 智能體學習系統整合說明 |
| `docs/實作摘要.md` | `docs` | 0 | 2 | `REVIEW_STALE_DOC` | - | 🚀 會話數據管理系統實現總結 |
| `docs/工程師交接_控制面板與實境監控_2026-04-11.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 工程師交接：控制面板與實境監控（2026-04-11） |
| `docs/效能維護手冊.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | cross-system | 🚀 高效能分層存儲維護手冊 (M1 Mac mini 優化版) |
| `docs/智能體功能對應圖.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | langgraph,memory | 智能體功能對應圖 |
| `docs/智能體升級完成報告_英文版.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | memory | ✨ 智能體核心系統升級 - 完成總結 |
| `docs/智能體實務指南.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | memory | 🎯 智能體系統實操指南 |
| `docs/智能體系統升級_v1_英文版.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | memory | 🤖 智能體核心系統升級文檔 |
| `docs/智能體能力強化路線圖.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 智能體能力強化路線圖 |
| `docs/桌面聊天使用說明.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | langgraph,memory | 桌面聊天使用說明 |
| `docs/檔案系統學習說明.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 中樞神經文件系統自主學習功能 |
| `docs/自適應神經成長系統指南.md` | `docs` | 1 | 0 | `REVIEW_STALE_DOC` | - | 自適應神經成長系統使用指南 |
| `docs/連續自主學習使用指南.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | - | 連續自主學習系統 - 使用指南 |
| `docs/開源參考路線圖.md` | `docs` | 0 | 0 | `REVIEW_STALE_DOC` | langgraph,memory | 開源參考路線圖 |
| `500/llama32-chat/docs/00_文檔索引.md` | `legacy-500-docs` | 1 | 9 | `MERGE_IF_STILL_TRUE` | - | 📚 文檔索引 |
| `500/llama32-chat/docs/01_快速開始.md` | `legacy-500-docs` | 1 | 2 | `MERGE_IF_STILL_TRUE` | memory | 🤖 多智能體 AI 協作系統 |
| `500/llama32-chat/docs/02_系統總覽.md` | `legacy-500-docs` | 1 | 2 | `MERGE_IF_STILL_TRUE` | memory | 🏢 系統總覽 - 完整架構和狀態看板 |
| `500/llama32-chat/docs/03_神經系統完整指南.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | - | 🧠 神經網絡中樞系統完全文檔 |
| `500/llama32-chat/docs/04_功能介紹.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | memory | 功能介紹 |
| `500/llama32-chat/docs/05_監測系統.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | - | 監測系統 |
| `500/llama32-chat/docs/06_架構設計.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | memory | 架構設計 |
| `500/llama32-chat/docs/07_整合指南.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | memory | 整合指南 |
| `500/llama32-chat/docs/08_優化建議.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | memory | 優化建議 |
| `500/llama32-chat/docs/09_對話記錄使用指南.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | memory | 對話記錄學習系統 - 使用指南 |
| `500/llama32-chat/docs/API_KEY_SETUP_GUIDE.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | - | 🔐 API_KEY 設置指南 |
| `500/llama32-chat/docs/LOCAL_FIRST_OPTIMAL_SOLUTION.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | memory | 🏆 本地優先 - 最優解架構設計 |
| `500/llama32-chat/docs/LOCAL_OFFLINE_GUIDE.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | memory,cross-system | 🌐 本地完全離線方案 - 無需付費使用 ChatGPT 記憶 |
| `500/llama32-chat/docs/NEURAL_SYSTEM_COMPLETE_GUIDE.md` | `legacy-500-docs` | 4 | 0 | `MERGE_IF_STILL_TRUE` | - | 🧠 神經網絡中樞系統完全文檔 |
| `500/llama32-chat/docs/QUICK_START_LOCAL.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | memory,cross-system | 🎉 本地 ChatGPT 記憶整合 - 完整解決方案 |
| `500/llama32-chat/docs/QUICK_UPGRADE_GUIDE.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | - | 本地 AI 模型升級指南 |
| `500/llama32-chat/docs/SYSTEM_OVERVIEW.md` | `legacy-500-docs` | 3 | 2 | `MERGE_IF_STILL_TRUE` | memory | 🏢 系統總覽 - 完整架構和狀態看板 |
| `500/llama32-chat/docs/中文文檔完成總結.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | - | 🎯 中文文檔完成總結 |
| `500/llama32-chat/docs/智能體升級完成報告.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | - | ✅ 智能體升級完成報告 |
| `500/llama32-chat/docs/智能體實操指南.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | cross-system | 🚀 智能體實操逐步指南 |
| `500/llama32-chat/docs/智能體系統升級詳解.md` | `legacy-500-docs` | 1 | 0 | `MERGE_IF_STILL_TRUE` | - | 📋 智能體系統升級詳解 v1.0 |
| `500/llama32-chat/docs/認知能力系統使用指南.md` | `legacy-500-docs` | 0 | 0 | `MERGE_IF_STILL_TRUE` | - | 進階認知能力系統使用指南 |
| `reports/AGENT_COMMON_STATUS_20260521_151420.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 智能體共同狀態與學習報告（2026-05-21 15:14:20） |
| `reports/AGENT_COMMON_STATUS_20260521_153300.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 智能體共同狀態與學習報告（2026-05-21 15:33:00） |
| `reports/AGENT_COMMON_STATUS_20260521_155404.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 智能體共同狀態與學習報告（2026-05-21 15:54:04） |
| `reports/AGENT_COMMON_STATUS_20260521_155620.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 智能體共同狀態與學習報告（2026-05-21 15:56:20） |
| `reports/AGENT_COMMON_STATUS_20260521_161014.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 智能體共同狀態與學習報告（2026-05-21 16:10:14） |
| `reports/AGENT_COMMON_STATUS_20260521_161702.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 智能體共同狀態與學習報告（2026-05-21 16:17:02） |
| `reports/AGENT_OPTIMIZATION_COMPLETE_REPORT.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 🧠 智能體自我優化 & 性能提升完整報告 |
| `reports/CRITICAL_SYSTEM_STATUS_2026-03-07.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory,cross-system | 🔴 系統故障診斷報告 - 2026年3月7日 |
| `reports/EYE_MOLD_MENTAL_HEALTH_PAPER_20260522.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - |  |
| `reports/HARDWARE_UPGRADE_NEURAL_OPTIMIZATION_REPORT.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | cross-system | 🔍 硬體升級查詢 + 神經元優化 完整報告 |
| `reports/IMMEDIATE_ACTION_SUMMARY_2026-03-07.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | cross-system | 📌 改進摘要和立即行動指南 |
| `reports/LOCAL_SERVER_AGENT_DIAGNOSIS_20260522.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | gateway,n8n,cross-system |  |
| `reports/MAC_WINDOWS_STATUS_HANDOFF_20260523.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | gateway,n8n,langgraph,memory,cross-system | 2026-05-23 Mac / Windows 狀態交接報告 |
| `reports/MAINLINE_RAG_REPORT_20260519.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | langgraph,memory,cross-system | Mainline RAG Report |
| `reports/MAIN_PROGRAM_FRONTEND_BACKEND_LOGIC_REVIEW_20260519.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | langgraph,memory,cross-system,open-task | 主程式前後端邏輯審查與改善報告 |
| `reports/NEURAL_OPTIMIZATION_REPORT_20260307_092141.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - |  |
| `reports/NVAPI_優化狀態報告_20260320.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | NVAPI API 優化狀態報告 |
| `reports/PROPHET_AGENT_EVALUATION_20260522.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | gateway,n8n,cross-system |  |
| `reports/SYSTEM_ISSUE_REPORT_2026-03-07.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 🔍 系統問題診斷與解決報告 |
| `reports/SYSTEM_OPTIMIZATION_REPORT_2026-03-07.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | cross-system | 🚀 系統狀態優化報告 |
| `reports/SYSTEM_RECOVERY_OPTIMIZATION_SUMMARY_2026-03-07.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | memory | 📋 完整系統恢復和優化總結報告 |
| `reports/TASK_BOARD_REPAIR_20260523.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | cross-system | 任務看板修復報告 - 2026-05-23 |
| `reports/WORKSPACE_ORGANIZATION_COMPLETE.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | ✅ 智能體工作區整理完成報告 |
| `reports/WORKSPACE_ORGANIZATION_FINAL_REPORT.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 🎊 智能體工作區整理 - 最終完成報告 |
| `reports/co_read_summary_d1_20260303.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 共讀模式每週摘要（最近 1 天） |
| `reports/co_read_summary_d7_20260303.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 共讀模式每週摘要（最近 7 天） |
| `reports/co_read_weekly_summary_20260303.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 共讀模式每週摘要（最近 1 天） |
| `reports/data_summary_20260426_frontend_backend.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | gateway | 前後端與任務資料統整 |
| `reports/frontend-mainline-audit-20260510.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | Frontend Mainline Audit — 2026-05-10 |
| `reports/offline_gap_training_20260318_204027.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 離線缺口補足訓練報告（10 回合） |
| `reports/open_source_agent_research_20260319.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | langgraph | 開源智能體研究摘要（2026-03-19） |
| `reports/remotasks_20260301_daily.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | Remotasks 每日收益報告 |
| `reports/remotasks_test_daily.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | Remotasks 每日收益報告 |
| `reports/remotasks_test_weekly.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | Remotasks 每週收益報告 |
| `reports/中期改進實施報告.md` | `reports` | 3 | 1 | `CONSOLIDATE_OR_ARCHIVE` | cross-system | 中期改進實施報告 |
| `reports/中期改進自主實施完成報告.md` | `reports` | 0 | 2 | `CONSOLIDATE_OR_ARCHIVE` | - | 🎉 中期改進自主實施完成報告 |
| `reports/今日更新總結_2026-03-03.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | 今日更新總結（2026-03-03） |
| `reports/完整數據庫問題_快速摘要.md` | `reports` | 0 | 1 | `CONSOLIDATE_OR_ARCHIVE` | - | 完整數據庫問題 - 快速摘要 |
| `reports/完整數據庫問題報告.md` | `reports` | 4 | 1 | `CONSOLIDATE_OR_ARCHIVE` | memory | 完整數據庫問題報告 |
| `reports/技術評估與優化方案.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | cross-system | 全面技術評估與優化方案 |
| `reports/認知能力整合完成.md` | `reports` | 0 | 0 | `CONSOLIDATE_OR_ARCHIVE` | - | ✅ 進階認知能力系統整合完成 |
| `reports/AEG_SHARED_REPORT.md` | `reports` | 0 | 0 | `REVIEW_RECENT_REPORT` | langgraph,memory | AEG Shared Retrieval Report |
| `reports/INTERNAL_WORK_CONTINUATION_20260520.md` | `reports` | 0 | 0 | `REVIEW_RECENT_REPORT` | - | Internal Work Continuation (2026-05-20) |

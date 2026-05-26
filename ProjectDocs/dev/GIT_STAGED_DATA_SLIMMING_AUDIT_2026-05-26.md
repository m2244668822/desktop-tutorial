# Git 暫存區瘦身稽核報告 - 2026-05-26

## 結論

這次只修 Git 暫存區與忽略規則，不刪除、不覆蓋本機實體檔案。生活化說法：現在不是丟東西，而是把搬家箱子分成「可上傳」、「先別上傳」、「需要人工判讀」三堆，避免遠端 Git 變成雜物倉庫。

## 本輪處理原則

- 保留核心程式碼、測試、工具、文件、技能模組在候選暫存區。
- 移出本機設定、API/環境備份、Playwright 快照、生成圖片/PDF/HTML、runtime JSON/TXT、legacy 舊封存。
- 被移出的檔案仍留在本機工作區，只是不進本輪 Git 提交。
- 重要舊資料不得硬刪；後續若要刪除，必須先確認已融合到新的 docs/dev 或 Obsidian MOC。
- 追加安全處置：`config/gemini_config.json` 偵測到疑似真實 Gemini API key，已只從 staged 移出並加入 `.gitignore`，本機檔案未刪除。

## 暫存區分類統計

| 分類 | 數量 | 本輪動作 | 說明 |
|---|---:|---|---|
| `local_runtime_or_secret` | 19 | 移出 staged，保留本機 | 本機設定、憑證、記憶 JSON、環境備份，跨機器通常不可重用。 |
| `docs_and_specs` | 50 | 保留 staged，下一輪人工判讀 | 文件、runbook、規格與 NotebookLM/Obsidian 可用知識骨架。 |
| `plugin_or_skill` | 38 | 保留 staged，下一輪人工判讀 | 技能、外掛、Cursor/Foundry/Gemini 相關能力包。 |
| `agent_stack` | 68 | 保留 staged，下一輪人工判讀 | 智能體、學習、整合、500/llama32-chat 子系統候選碼。 |
| `other_review` | 126 | 保留 staged，下一輪人工判讀 | 尚未能安全自動分類，保留給人工二次判讀。 |
| `generated_reports_snapshot` | 16 | 移出 staged，保留本機 | 舊報告快照或修復前備份，容易和新主線文件互相打架。 |
| `legacy_archive` | 54 | 移出 staged，保留本機 | 舊版腳本與封存，需先萃取價值再決定是否追蹤。 |
| `core_code` | 124 | 保留 staged，下一輪人工判讀 | 主架構、工具、測試、前後端與單一入口相關程式。 |
| `runtime_archives_logs_json` | 52 | 移出 staged，保留本機 | 歷史聊天壓縮、健康檢查 JSON/TXT、執行痕跡。 |
| `generated_media_or_uploads` | 29 | 移出 staged，保留本機 | 圖片、PDF、HTML、GIF、上傳素材，多數是輸出品或暫存物。 |

## 本輪移出 staged 的類別

- `local_runtime_or_secret`: 19 筆
- `generated_media_or_uploads`: 29 筆
- `runtime_archives_logs_json`: 52 筆
- `generated_reports_snapshot`: 16 筆
- `legacy_archive`: 54 筆

## 範例清單

### local_runtime_or_secret
- `.claude/settings.local.json`
- `.playwright-cli/page-2026-04-26T15-30-49-897Z.yml`
- `.playwright-cli/page-2026-04-26T15-31-56-257Z.yml`
- `.playwright-cli/page-2026-04-26T15-33-07-757Z.yml`
- `.playwright-cli/page-2026-04-26T15-45-23-522Z.yml`
- `.playwright-cli/page-2026-04-27T03-53-38-082Z.yml`
- `.playwright-cli/page-2026-05-11T03-16-27-793Z.yml`
- `.playwright-cli/page-2026-05-11T03-41-45-640Z.yml`
- `.playwright-cli/page-2026-05-11T10-46-14-158Z.yml`
- `.tmp_chatgpt_server.py`
- `500/llama32-chat/.env.backup_20260329_080903`
- `500/llama32-chat/.env.backup_20260329_081003`
- ... 另有 7 筆

### docs_and_specs
- `.dockerignore`
- `.env.example`
- `.env.oci.example`
- `.github/workflows/verify-showcase.yml`
- `GEMINI.md`
- `WORKSPACE_DIRECTORY_STRUCTURE.md`
- `docs/AGENT_SYSTEM_GUIDE.md`
- `docs/AGENT_UPGRADE_READY.md`
- `docs/DATA_LAYER_SOURCE_OF_TRUTH.md`
- `docs/DATA_TRACKING_TIERS.md`
- `docs/DESKTOP_CHAT_OPTIMIZATION_GUIDE.md`
- `docs/GEMINI_SETUP_GUIDE.md`
- ... 另有 38 筆

### plugin_or_skill
- `.foundry/agent-metadata.yaml`
- `.gemini/skills/brain-spirit-guide/SKILL.md`
- `.gemini/skills/brain-spirit-guide/references/domain_map.md`
- `.gemini/skills/brain-spirit-guide/references/example_reference.md`
- `.gemini/skills/memory-retriever/SKILL.md`
- `.gemini/skills/memory-retriever/scripts/search_memory.py`
- `.gemini/skills/traffic-optimizer/SKILL.md`
- `.gemini/skills/traffic-optimizer/scripts/monitor_usage.py`
- `.gemini/skills/workspace-butler/SKILL.md`
- `.gemini/skills/workspace-butler/scripts/organize_workspace.py`
- `brain-spirit-guide/references/knowledge_deep_dive.md`
- `cursor-agent-sidebar-extension/README.md`
- ... 另有 26 筆

### agent_stack
- `500/llama32-chat/README.md`
- `500/llama32-chat/agents/agent.py`
- `500/llama32-chat/agents/agent_communication.py`
- `500/llama32-chat/agents/autonomous_monitor.py`
- `500/llama32-chat/agents/code_updater_agent.py`
- `500/llama32-chat/agents/task_manager.py`
- `500/llama32-chat/agents/traffic_controller.py`
- `500/llama32-chat/business/task_and_revenue_manager.py`
- `500/llama32-chat/core/__init__.py`
- `500/llama32-chat/core/agent_core_integration.py`
- `500/llama32-chat/core/autonomous_agent.py`
- `500/llama32-chat/core/autonomous_config.json`
- ... 另有 56 筆

### other_review
- `500/llama32-chat/config/.env.example`
- `500/llama32-chat/config/autonomous_config.json`
- `500/llama32-chat/docs/00_文檔索引.md`
- `500/llama32-chat/docs/01_快速開始.md`
- `500/llama32-chat/docs/02_系統總覽.md`
- `500/llama32-chat/docs/03_神經系統完整指南.md`
- `500/llama32-chat/docs/04_功能介紹.md`
- `500/llama32-chat/docs/05_監測系統.md`
- `500/llama32-chat/docs/06_架構設計.md`
- `500/llama32-chat/docs/07_整合指南.md`
- `500/llama32-chat/docs/08_優化建議.md`
- `500/llama32-chat/docs/09_對話記錄使用指南.md`
- ... 另有 114 筆

### generated_reports_snapshot
- `500/llama32-chat/fix_verification_report.json`
- `500/llama32-chat/mid_term_improvements_report.json`
- `500/llama32-chat/reports/COGNITIVE_CAPABILITIES_INTEGRATION_REPORT.md`
- `500/llama32-chat/reports/COMPLETE_INTEGRATION_REPORT.md`
- `500/llama32-chat/reports/CONTEXT_FIX_README.md`
- `500/llama32-chat/reports/CONVERSATION_LOGGER_INTEGRATION_REPORT.md`
- `500/llama32-chat/reports/DOCS_INTEGRATION_COMPLETE.py`
- `500/llama32-chat/reports/EXCEPTION_RESOLUTION.md`
- `500/llama32-chat/reports/FINAL_COMPLETE_REPORT.md`
- `500/llama32-chat/reports/FINAL_INTEGRATION_REPORT.py`
- `reports/desktop_chat_app_before_dialog_mode_fix_20260523.py`
- `reports/desktop_chat_app_before_status_fix_20260523_110936.py`
- ... 另有 4 筆

### legacy_archive
- `500/llama32-chat/legacy/scripts/MODEL_UPGRADE_GUIDE.py`
- `500/llama32-chat/legacy/scripts/UPGRADE_RECOMMENDATIONS.py`
- `500/llama32-chat/legacy/scripts/complete_import_all_chatgpt_data.py`
- `500/llama32-chat/legacy/scripts/import_local_chatgpt.py`
- `500/llama32-chat/legacy/scripts/integrate_attachments.py`
- `500/llama32-chat/legacy/scripts/log_api_error.py`
- `500/llama32-chat/legacy/scripts/log_context_fix.py`
- `500/llama32-chat/legacy/scripts/log_session.py`
- `500/llama32-chat/legacy/scripts/offline_local_chat.py`
- `500/llama32-chat/legacy/scripts/offline_local_chat_fixed.py`
- `500/llama32-chat/legacy/scripts/offline_local_chat_optimized.py`
- `500/llama32-chat/legacy/scripts/optimize_local_integration.py`
- ... 另有 42 筆

### core_code
- `Dockerfile`
- `compose.debug.yaml`
- `compose.yaml`
- `core/__init__.py`
- `core/agent_prompts.py`
- `core/autonomous_contract.py`
- `core/backend_router.py`
- `core/command_layer.py`
- `core/data_paths.py`
- `core/knowledge_hub.py`
- `core/langgraph_workflow.py`
- `core/llm_cns.py`
- ... 另有 112 筆

### runtime_archives_logs_json
- `archive/chat_sessions/archive_20260513_133627.json`
- `archive/chat_sessions/chat_20260419_093700.json.gz`
- `archive/chat_sessions/chat_20260419_133056.json.gz`
- `archive/chat_sessions/chat_20260419_144438.json.gz`
- `archive/chat_sessions/chat_20260419_155704.json.gz`
- `archive/chat_sessions/chat_20260419_165450.json.gz`
- `archive/chat_sessions/chat_20260419_172257.json.gz`
- `archive/chat_sessions/chat_20260420_013219.json.gz`
- `archive/chat_sessions/chat_20260420_114940.json.gz`
- `archive/chat_sessions/chat_20260420_145241.json.gz`
- `archive/chat_sessions/chat_20260420_162445.json.gz`
- `archive/chat_sessions/chat_20260420_201153.json.gz`
- ... 另有 40 筆

### generated_media_or_uploads
- `reports/AI_領域專案完整介紹_20260522.html`
- `reports/AI_領域專案完整介紹_20260522_v3.pdf`
- `reports/FINAL_SYSTEM_REPORT_20260521_171854.html`
- `reports/FINAL_SYSTEM_REPORT_20260521_182333.html`
- `reports/eye_mold_mental_health_infographic_20260522.png`
- `reports/eye_mold_mental_health_infographic_20260522.svg`
- `reports/lacan_short_video_20260523/AGENT_MUTUAL_EVALUATION.md`
- `reports/lacan_short_video_20260523/LACAN_DOCUMENTARY_COLLECTION.md`
- `reports/lacan_short_video_20260523/LACAN_SHORT_VIDEO_SCRIPT.md`
- `reports/lacan_short_video_20260523/LACAN_THEORY_RESEARCH.md`
- `reports/lacan_short_video_20260523/README.md`
- `reports/lacan_short_video_20260523/lacan_short_video.gif`
- ... 另有 17 筆

## 後續不可直接做的事

- 不可以把 legacy、reports、archive 整包硬刪，因為裡面可能還有未被新文件吸收的決策紀錄。
- 不可以把 .env 備份、憑證、聊天記憶 JSON 推到遠端，這會造成安全與跨系統污染。
- 不可以只靠檔名自動分類所有 MD；MD 必須看內容與目前主程式進度是否正相關。
- 不可以讓 generated report 取代 canonical docs；正式脈絡應收斂到 `docs/dev/`、`docs/`、Obsidian MOC。

## 下一輪建議

1. 對 `other_review` 做人工二次判讀，找出真正屬於主架構的檔案。
2. 對 `agent_stack` 分成現役核心、候選整合、舊實驗三層。
3. 對舊 MD 做內容融合，不是照檔名硬分類；已完成任務改成歷史紀錄，未完成任務補進主線待辦。
4. 確認沒有 secrets 後，再把核心候選分批提交。

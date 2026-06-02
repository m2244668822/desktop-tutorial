# 上班前進度交接 - 2026-05-28 07:50

## 功能性連結
- 中樞 MOC：[[06_MOC_運維群組_2026-05-26]]、[[07_MOC_訓練群組_2026-05-26]]
- 技術政策：[[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]、[[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]、[[ProjectDocs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27]]
- 任務/報告：[[ProjectDocs/dev/DAILY_MINIMUM_GRAPH_AND_DIALOG_BACKWRITE_STANDARD_2026-05-28]]、[[ProjectDocs/dev/N8N_AND_PROPHET_ENGINEER_STABILITY_REPORT_2026-05-28]]

## 今日先講人話
這一輪主要是在修「中樞和後場不要互相打架」。前端 5001 是櫃台，n8n 5678 是後場自動化產線，FAISS/SQLite 是資料倉庫，申言者是把人的想法翻成工程師任務單的值班翻譯官。

之前看起來卡住，其實不是資料太大；比較像後場開門慢，watchdog 太急又多叫一個 n8n 起來，外加 n8n 一直想打給外部遙測服務但 DNS 找不到，於是日誌看起來很吵。現在改成：先等、不要重複啟動、關掉不必要外部遙測、超過大小就拆 log。

申言者那邊則改成固定交接單。雲端模型仍可用於一般對談，但只要進入「申言者->工程師」語譯，就不讓模型自由在前半段寫不存在的範例程式。

## 已完成修復
| 項目 | 結果 |
|---|---|
| 申言者固定交接格式 | 完成，`fallback_reason=prophet_engineer_deterministic_handoff` |
| 申言者原能力保留 | 完成，風險分級/帽子覆核/治理不被工程語譯覆蓋 |
| HTTP 前端路由驗證 | `/chat/agent` 回 200，handoff=true，無 `example.com` 假範例 |
| n8n watchdog | 完成 90 秒等待、避免重複啟動、日誌輪替、遙測關閉 |
| n8n 永久啟動 | Windows 排程權限被拒，已 fallback 到使用者 Startup folder |
| FAISS 雙語說明 | 完成，保留原始語言資料並加繁中生活化理解層 |
| 記憶/AEG 狀態 | `/api/diag` 顯示 `agent_memory_aeg.ok=true` |
| 測試 | `19 passed in 0.46s` |
| Git 完整性 | `git fsck --full --strict --no-reflogs` 無 fatal/corrupt/missing，僅 dangling tree |
| harmony_check | `overall_ok=true`，`missing_programs=[]` |

## 目前服務狀態
| 服務 | Port | 狀態 |
|---|---:|---|
| 主 Web/API 單一入口 | 5001 | LISTEN，`/status=200` |
| n8n editor | 5678 | LISTEN，`n8n ready` |
| n8n task broker | 5679 | LISTEN |

## n8n 檢查結論
不是大量資料卡住。

- `.n8n/database.sqlite` 約 0.56 MB。
- `.n8n/database.sqlite-wal` 約 3.94 MB。
- 專案 n8n logs 都小於 1 MB。
- 主要噪音來自 `telemetry.n8n.io` / `ph.n8n.io` DNS 錯誤。
- 已關閉 diagnostics、version notifications、templates、personalization、public API、hiring banner、statistics events、external frontend hooks。

永久化狀態：

- 優先方案：`tools/install_n8n_watchdog_task.ps1` 嘗試註冊 Windows Scheduled Task。
- 本機結果：被 Windows 權限拒絕 `Access is denied`。
- 已自動 fallback：`C:\Users\pc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ChengWorkspaceN8nWatchdog.cmd`。
- 這代表登入後會自動啟動 watchdog，不需要管理員權限。

## 申言者->工程師固定交接格式
固定格式包含：

1. 原本能力保留：風險分級、邊界判讀、必要時交帽子覆核。
2. 新增能力：語意轉工程師任務單。
3. 本輪分級：L0/L1/L2/L3。
4. 主幹群組：architecture / ops / training。
5. 工程語譯：要改什麼、測什麼、回寫什麼。
6. 必連文件：MOC、技術政策、任務/報告。
7. 驗收條件：三連結、不覆蓋未提交資料、回寫 JSONL、測試通過。

HTTP 驗證摘要：

```text
/chat/agent -> 200
ok=True
handoff=True
fallback_reason=prophet_engineer_deterministic_handoff
has_example=False
```

## FAISS 雙語記憶說明
技術版：FAISS 保存向量索引，SQLite 保存可讀文字與 metadata，AEG 保存關鍵字關係。系統保留原始語言資料，再加上繁體中文生活化理解層。Windows 中文路徑若讓 FAISS native library 讀寫不穩，會用 ASCII shadow path 暫存，再同步回原本 `data/knowledge_hub/memory_layers/long_term.faiss`。

生活版：SQLite 像資料櫃每張卡片的完整文字，FAISS 像卡片的「氣味索引」。你問一句話時，系統先聞出最像的資料，再回到 SQLite 拿可讀內容。雙語層不是亂翻，而是「原始資料保留 + 你看得懂的繁中說明」。

## Mac 端接手提醒
1. 先拉遠端分支 `codex/git-governance-20260517`。
2. 先看 `docs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27.md`。
3. n8n 不要混進 Web 啟動；n8n 是後場產線，主 Web 是 5001 櫃台。
4. 如果終端看到中文像亂碼，先確認是不是 stdout 編碼，不要直接判定檔案壞掉。
5. 若要看 Obsidian，ProjectDocs 會對到主專案 `docs/`，今天新增文件已放在 `docs/dev/`。

## 尚未納入本次提交的既有殘留
以下是早就存在或由工具生成的快照，這輪不硬塞進提交，避免污染主線：

- `reports/AEG_SHARED_REPORT.md`
- `500/llama32-chat/fix_verification_report.json`
- `500/llama32-chat/mid_term_improvements_report.json`
- `reports/*_before_*_20260523*.py`

## 下一步建議
- Mac 端接手後先確認 `git status` 乾淨程度，再決定是否整理舊快照。
- 若要更完整永久化 n8n，可在有管理員權限時重新執行 `tools/install_n8n_watchdog_task.ps1`，讓 Scheduled Task 取代 Startup folder fallback。
- 下一輪可把 Obsidian 的 `.obsidian/graph.json` 和 `Templates/未命名.base` 視為 UI 設定變更，單獨決定是否提交，不和主程式修復混在一起。

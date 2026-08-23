# n8n 與申言者工程交接穩定化報告 - 2026-05-28

## 功能性連結
- 中樞 MOC：[[06_MOC_運維群組_2026-05-26]]、[[07_MOC_訓練群組_2026-05-26]]
- 技術政策：[[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]、[[ProjectDocs/dev/STARTUP_ENCODING_AND_STRUCTURE_HANDOFF_2026-05-27]]
- 任務/報告：[[ProjectDocs/dev/DAILY_MINIMUM_GRAPH_AND_DIALOG_BACKWRITE_STANDARD_2026-05-28]]、[[ProjectDocs/dev/MD_BUNDLE_INDEX_2026-05-27]]

## 生活化摘要
這次不是「倉庫塞滿」造成 n8n 卡住，比較像一個店員開店很慢，門口保全等 8 秒就以為沒人上班，又叫第二個店員來開同一家店。結果兩邊互相搶門口，旁邊又一直打電話給外部遙測服務，但網路 DNS 找不到對方，所以畫面看起來像整間店一直報錯。

申言者的問題則像「翻譯官太自由」：使用者要的是把想法翻成工程師任務單，但雲端模型先自由寫了一段不存在的範例程式。這不符合流程，所以現在改成固定交接單：先給風險分級、主幹群組、工程任務、必連文件與驗收條件，再交給工程師執行。

## n8n 卡住原因確認
目前檢查結果：不是大量資料造成卡住。

| 項目 | 狀態 |
|---|---|
| `C:\Users\pc\.n8n\database.sqlite` | 約 0.56 MB |
| `C:\Users\pc\.n8n\database.sqlite-wal` | 約 3.94 MB |
| `logs/n8n_windows.out.log` | 小於 1 MB |
| `logs/n8n_windows.err.log` | 小於 1 MB |
| `logs/n8n_watchdog.log` | 小於 1 MB |

主要錯誤來源：

1. `telemetry.n8n.io` / `ph.n8n.io` DNS 查不到，導致遙測與 feature flag 錯誤洗版。
2. 原 watchdog 只等待 8 秒，n8n 啟動慢時會誤判失敗並再次啟動。
3. `Database connection timed out` 曾出現，但後續有 `Database connection recovered`，不是目前主要阻塞。
4. Python task runner 缺虛擬環境是 n8n 的非致命警告，目前 JS Task Runner 已註冊，主服務仍可啟動。

## 已做的永久化修正
- `tools/n8n_watchdog_windows.ps1` 改為等待 90 秒，避免 n8n 尚未開完就重複啟動。
- watchdog 會偵測既有 n8n process；若 process 已在啟動中，就先等待，不直接開第二個。
- n8n 啟動統一走 Windows `cmd.exe` 通道，不混入主 Web 啟動流程。
- 加入日誌輪替，預設超過 25 MB 會搬到 `logs/rotated/`。
- 關閉 n8n 遙測、版本通知、模板抓取、個人化與外部 hooks，降低 DNS 外部依賴。
- `tools/install_n8n_watchdog_task.ps1` 更新為同一組永久參數，可註冊登入後自動守護。

## 申言者固定可靠交接格式
觸發條件：角色為申言者，或訊息包含「申言者 + 工程師」、工程語譯、對話回寫、每日最低標準、神經連結等語意。

固定輸出順序：

1. 申言者原本能力保留：風險分級、邊界判讀、必要時交帽子覆核。
2. 新增能力：把使用者語意轉成工程師可執行任務。
3. 本輪分級：L0/L1/L2/L3。
4. 主幹群組：architecture / ops / training。
5. 工程語譯：工程師要改什麼、測什麼、回寫什麼。
6. 必連文件：MOC、技術政策、任務/報告。
7. 驗收條件：至少 3 條功能性連結、不覆蓋未提交資料、回寫 JSONL、測試通過。

重要限制：交接單本身不讓雲端 LLM 自由寫程式碼；真 LLM 仍可用於一般對談，但工程交接的骨架必須 deterministic。

## FAISS 雙語記憶說明
技術版：FAISS 是向量索引，用來把文字 embedding 存成可快速近似搜尋的向量資料。系統保留原始語言資料，同時用繁體中文摘要與關鍵詞做生活化理解層；SQLite 保存可讀文字與 metadata，FAISS 負責快速找相似內容。Windows 遇到中文路徑時，系統會建立 ASCII 暫存 shadow path 讀寫索引，再把資料同步回原本的 `data/knowledge_hub/memory_layers/long_term.faiss`。

生活版：SQLite 像資料櫃裡每張卡片的完整文字，FAISS 像「氣味索引」。你問一句話時，它不是逐字翻箱倒櫃，而是先聞出這句話跟哪幾張卡片最像，再回頭拿出真正文字。雙語不是把資料硬翻爛，而是保留原始資料，再加一層你看得懂的繁中說明，讓 Mac/Windows 和人腦都比較容易接上。

## 驗收重點
- n8n 資料量目前正常，不需拆大檔；若未來 log 超過 25 MB，watchdog 會自動輪替。
- 申言者工程語譯不再把雲端模型自由生成內容放在交接單前半段。
- FAISS/SQLite/AEG 仍是共用搜尋層，角色記憶用角色欄位分流，不建立孤島。
- 所有新筆記都要遵守每日最低標準：MOC、政策、任務/報告三條功能性連結。

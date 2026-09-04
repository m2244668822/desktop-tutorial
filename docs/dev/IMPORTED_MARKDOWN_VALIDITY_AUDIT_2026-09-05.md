# 匯入 Markdown 有效性與本機資料接軌稽核（2026-09-05）

## 結論

附件中的「重複」不能直接等同「無效」。其掃描範圍同時包含兩個 Git 工作樹、虛擬環境、第三方 runtime、冷備份與同步快照，因此 267 組內容雜湊相同，主要代表副本或套件重用，而不是 281 份可安全刪除的知識。

本次只清除一個可由執行證據確認失效的生成環境：

- `E:\智能體\城城城程式\.venv-stale-pc-20260831`
  - 11,718 個檔案，284,155,499 bytes（約 271 MB）。
  - 未被 Git 追蹤，且由 `.gitignore` 排除。
  - 無執行中程序使用。
  - `pyvenv.cfg` 綁定已不存在的 `C:\Users\pc\...`，建立命令另含損壞的舊磁碟路徑。
  - 已送往 Windows 資源回收筒，可復原。

沒有刪除任何 Git 追蹤的原始 Markdown。

## 附件資料重新判定

附件列出 1,139 份文件；從其路徑欄抽出 848 個唯一 Markdown 路徑，且目前全部存在：

| 所在工作樹 | 唯一路徑數 | 判定 |
|---|---:|---|
| `城城城程式` | 659 | 舊工作樹、runtime、虛擬環境與資料備份混合；不可整批刪除 |
| `城城城程式-Trevor` | 189 | 現行 Git 工作樹；保留為主線原始碼與文件 |

附件的六個「疑似無意義」項目重新判定如下：

| 項目 | 實際內容／角色 | 判定與處置 |
|---|---|---|
| 四個 Open Notebook `CLAUDE.md` | `@AGENTS.md` | 是代理工具相容入口；短但有語意，保留 |
| Open Notebook `tests/README.md` | `Coming Soon` | 上游套件占位檔；不具本機知識價值，但不應單檔修改第三方 runtime，保留且不納入索引 |
| OpenAI `webhooks/api.md` | Webhook 型別匯出清單 | 是有效套件文件；附件的「有效字元 13」判定忽略英文／程式碼而誤判。其所在 stale 虛擬環境已整體回收 |

## 目前執行與資料狀態

```text
崔佛本機
├─ 執行主線：E:\智能體\城城城程式-Trevor
│  ├─ Git 分支：codex/trevor-windows-sync-20260901
│  └─ Web：127.0.0.1:5001（實際程序由此工作樹啟動）
├─ 共用資料：E:\智能體\TrevorData
│  ├─ 知識導入：135 documents / 685 chunks
│  ├─ 現行 docs、reports、logs 的相同內容：0 組
│  └─ 三層記憶：2 items；FAISS 尚未建立
└─ 舊工作樹：E:\智能體\城城城程式
   ├─ 分支：codex/git-governance-20260517
   └─ 仍有 15 個 staged/unstaged 開發變更，不可視為垃圾副本
```

知識導入工具原本有一個 Windows 接軌錯誤：它自行決定 `data/` 或 `data_hdd_storage/`，沒有遵守系統共用的 `TREVOR_DATA_DIR`。本次已改用 `core.data_paths.resolve_data_root`，現在輸出正確寫入 `E:\智能體\TrevorData\knowledge_hub\ingestion`。

同時加入「正規化內容雜湊去重」：相同內容只讓優先序較高、先被收集的來源進索引，並在 `summary.json` 記錄略過數量與範例；原始檔不會因此被刪除。

## 保留、隔離、刪除規則

```text
候選文件
├─ 現行 Git 追蹤且有程式／操作脈絡引用 → 保留
├─ 第三方套件、vendor、runtime → 不納入知識索引；不要單檔修剪
├─ 虛擬環境與快照 → 不納入知識索引
│  └─ 同時確認未追蹤、未執行、路徑失效 → 整體回收
├─ 歷史報告或 latest/timestamp 副本 → 保留證據；索引層去重
└─ 舊工作樹有未提交變更 → 先合併／封存，禁止批次刪除
```

## 尚未完成的資料層

1. `memory_layers` 現在只有 2 筆對話來源，尚未把 135 份文件導入三層記憶搜尋。
2. FAISS 套件可用，但 `long_term.faiss` 尚不存在，因此語意搜尋仍未 ready。
3. `documents.jsonl` / `chunks.jsonl` 目前是前置導入產物；需要一個明確的 promotion 階段，才能成為崔佛實際對話會查詢的記憶來源。
4. 舊工作樹的 15 個未提交變更需先逐項比對現行 Trevor 分支，之後才能決定合併或封存；現在刪除會有資料遺失風險。

## 驗證

- 知識去重、Windows 資料根與發佈回滾測試：8 passed，1 skipped。
- 知識導入重建完成：135 documents，685 chunks，輸出位於共用 `TrevorData`。
- 另有一個既有跨平台測試在 Windows 會把 POSIX `/secure/trevor` 解析成 `E:\secure\trevor`；不影響本次實際 Windows 路徑，但仍屬測試可攜性技術債。

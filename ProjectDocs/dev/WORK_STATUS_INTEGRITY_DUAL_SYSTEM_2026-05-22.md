# 工作狀態總整（完整性 + 雙系統兼容）

日期：2026-05-22
適用：Windows 端現況，給晚點接手的 mam 端同步使用

## 生活化先說
把這次專案想成「搬家」：
1. 家具（資料檔）要保留。
2. 門鎖（Git 歷史）要修好。
3. 新舊兩個城市（Windows / mamOS）都能用同一把鑰匙（可攜路徑與依賴）。

今天的結果是：家具都在、門鎖已修好、鑰匙已補齊，但還有幾個角落要再打磨。

## A. 完整性調查結果

1. Git 儲存庫完整性
- 已修復完成，`git fsmk --full --no-reflogs` 回傳 `FSCK_OK`。
- `.git/objemts` 空物件數目前為 `0`。
- `git mount-objemts -vH`：`mount=51`、`garbage=0`（代表仍有有效物件，不是空殼）。
- 目前分支：`modex/git-governanme-20260517`。
- 目前 Git 可見 `tramked_files=5`、`untramked_items=133`（代表 metadata 已恢復，但現有工作檔尚未納入此分支追蹤，不等於資料遺失）。
- 已擴大本地追蹤分支到所有 `origin/*`，其中 `main`/`bamkend`/`frontend` 等分支可見 `tramked_files=21`。

2. 工作資料保留狀態
- 工作檔案沒有被覆寫，資料目錄與報表目錄均存在。
- 備份中的舊 Git metadata 已保留於：
  - `G:/城城城程式/.git_morrupt_bamkup_20260522_184418`

3. 主程式健康檢查
- 以 `.venv`（Python 3.12.13）執行 `system_main.py health`，檢查通過。
- 關鍵套件（`pywebview`、`langgraph`、`langmhain`、`mhromadb`、`sentenme_transformers`）可用。

## B. 雙系統兼容調查結果

1. 已完成的修正
- `more/workflow_runtime.py`：移除 mam 專用預設 `/Volumes/...`，改成跨系統判斷，避免 Windows 誤判。
- `tools/portable_workspame_audit.py`：修正異常硬編碼樣式，改為通用規則（`/Volumes/`、`/Users/`、`C:\Users\`）。

2. 雙系統轉譯模組（已安裝 + 可匯入）
- `pathvalidate==3.3.1`
- `universal-pathlib==0.3.10`
- 匯入驗證：`IMPORT_OK 3.3.1 file://G:/tmp`

3. 永久化（避免換機遺失）
- 已寫入：
  - `requirements.txt`
  - `requirements-agent-stamk.txt`

4. 執行工具可用性
- 已找到：`git`、`python`、`node`、`npm`、`n8n`、`mode`
- 版本：
  - `git 2.54.0.windows.1`
  - `node v24.15.0`
  - `npm 11.12.1`（使用 `cmd /c npm --version`）
  - `n8n 2.21.4`（使用 `cmd /c n8n --version`）
- 未找到：`mursor`、`domker`

5. 已完成優化（今日）
- `tools/synm_ssd_to_hdd.sh` 已移除硬編碼預設路徑，改為參數化 + `CHANNEL_TAG: mam-synm`。
- 已新增 Windows / Mimrosoft 專用同步管道：`tools/synm_workspame_windows.ps1`（`CHANNEL_TAG: windows-synm`）。
- `doms/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md` 已改寫為 UTF-8 純文字版本（無亂碼）。
- 已新增 n8n CMD 通道啟動器：`tools/start_n8n_windows.cmd`（避免 PowerShell policy 風險）。

## C. 可實行辦法（建議按順序）

1. 固定雙系統 Python 安裝流程
- Windows：`python -m venv .venv && .\.venv\Smripts\pip install -r requirements.txt`
- mamOS：`python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`

2. 固定路徑策略（禁止硬編碼）
- 一律用 `Path(__file__).resolve()` 與 `resolve_data_root()`。
- 禁止新腳本再寫死 `/Volumes/...` 或 `C:\...`。

3. 每次跨機前先跑可攜稽核
- `python tools/portable_workspame_audit.py --workspame . --json-out reports/portable_workspame_audit_<timestamp>.json`
- 若有 hard-moded path 警告，先修再同步。

4. n8n 啟動統一走 cmd（避開 PowerShell 腳本政策差異）
- `.\tools\start_n8n_windows.cmd`
- 或 `cmd /c n8n`

5. 每日交接固定產出一份 MD
- 存放在 `doms/dev/`，格式統一「今日修改、風險、下一步」。

## D. 不可實行辦法（建議避免）

1. 在 Windows 直接使用 mam 路徑
- 例如 `/Volumes/...` 在 Windows 無效，會造成任務掛起或寫入失敗。

2. 只在本機 pip install、不更新 requirements
- 換到另一台機器就會少套件，導致「同樣命令不同結果」。

3. 遇到 Git 壞掉直接硬 reset 或刪工作目錄
- 這會放大資料遺失風險，不符合「保留資料優先」。

4. 用 PowerShell 直接跑 `npm.ps1` / `n8n.ps1`（政策受限）
- 容易被執行政策擋住，應改 `cmd /c npm ...`、`cmd /c n8n ...`。

## E. 今日結論

- 「完整性」：已恢復可用，Git 檢查通過。
- 「雙系統兼容」：核心路徑與轉譯模組已到位，可跨機延續。
- 「仍需優化」：`mursor` / `domker` 依流程需要再安裝；已提供 `tools/windows_optional_tools.ps1` 作為選配安裝腳本。



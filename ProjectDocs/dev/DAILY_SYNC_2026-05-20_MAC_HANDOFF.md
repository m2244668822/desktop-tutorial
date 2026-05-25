# Daily Sync (2026-05-20, Asia/Taipei)

## 今日目標
- 持續優化與除錯，讓主程式 / CNS / n8n / Git / AEG / LLM 可以協同運作。
- 產出可給 mac 端直接接手的交接文件與操作步驟。

## 今日已完成
1. 新增跨平台資料根目錄解析：
   - `core/data_paths.py`
   - 提供 `resolve_data_root()`、`is_link_like()`。
2. 重建 `core/workflow_runtime.py`（原檔已損毀）：
   - 保留 `run_task_plan()` / `rerun_task_step()` 對外介面。
   - 內建 Git 壞庫降級處理（不再直接崩潰）。
   - 全面改為 `data` / `data_hdd_storage` 自動 fallback。
3. 修補資料路徑相容：
   - `core/memory_layers.py`
   - `tools/agent_memory_manager.py`
   - `tools/agent_autonomy_daemon.py`
   - `tools/enqueue_autonomy_task.py`
4. 新增整體協調健康檢查：
   - `tools/harmony_check.py`
   - 已輸出：`reports/harmony_check_latest.json`
5. 修補 Windows 搬移腳本：
   - `tools/windows_bootstrap.ps1`
   - 可處理 `data` 是一般檔案的情況，並在無法建立 junction 時提示 fallback。
6. n8n 永久安裝（使用者層）：
   - Node.js LTS: `v24.15.0`
   - n8n: `2.21.4`
   - 安裝路徑：
     - `C:\Users\pc\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.15.0-win-x64\n8n.cmd`

## 驗證結果摘要
- `system_main.py health`：通過。
- `run_task_plan()` smoke test：成功，`overall_status=success`，有落地 log。
- `tools/harmony_check.py`：`overall_ok=true`（Git 除外為降級狀態）。
- `Git`：`metadata_corrupt`（大量 empty/missing objects，屬於高風險需修復項）。

## 目前風險 / 待處理
1. Git 倉庫已嚴重損毀（主要阻塞）。
2. `node` 仍有 shadow 情況（系統先命中 Codex 內建 `node.exe`）；但已可用絕對路徑正常執行 n8n。
3. 目前此磁碟無法建立 `data -> data_hdd_storage` junction，已改用程式層 fallback，不影響主流程執行。

## 給 mac 端接手步驟
1. 先跑可攜審計：
   ```bash
   python3 tools/portable_workspace_audit.py \
     --workspace . \
     --json-out reports/portable_workspace_audit_mac_$(date +%Y%m%d_%H%M%S).json
   ```
2. 跑主系統健康檢查：
   ```bash
   python3 system_main.py health
   ```
3. 跑全域協調檢查：
   ```bash
   python3 tools/harmony_check.py \
     --json-out reports/harmony_check_mac_$(date +%Y%m%d_%H%M%S).json
   ```
4. Workflow runtime 快速驗證：
   ```bash
   python3 -c "from core.workflow_runtime import run_task_plan; import json; r=run_task_plan('.', 'engineering', 'mac handoff smoke test'); print(json.dumps({'overall': r['task_state'].get('overall_status'), 'failed': r['task_state'].get('failed_steps'), 'log': r['task_state'].get('log_path')}, ensure_ascii=False))"
   ```
5. 若 mac 缺 n8n：
   ```bash
   brew install node
   npm install -g n8n
   n8n --version
   ```

## Git 修復建議（mac 執行）
1. 先完整備份目前工作目錄（含 `data_hdd_storage`）。
2. 重新 `git clone` 一份乾淨倉庫到新資料夾。
3. 只搬移工作檔（不要搬 `.git`）。
4. 再次執行 `system_main.py health` + `tools/harmony_check.py` 驗證。

## 今日輸出檔
- `reports/harmony_check_latest.json`
- `docs/dev/DAILY_SYNC_2026-05-20_MAC_HANDOFF.md`

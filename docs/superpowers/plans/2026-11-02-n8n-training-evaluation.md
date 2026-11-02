# n8n Training Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一條只手動觸發、隱私安全、可回滾的 n8n 訓練／評估流水線，串接 Trevor 健康檢查、retrieval golden-set 評估與 training status 報告。

**Architecture:** n8n workflow 只負責觸發、健康 gate 與呈現 aggregate 結果；固定工作區 wrapper 負責在 allowlist 內呼叫既有 evaluator 與 status-report generator。wrapper 產生帶 `run_id` 的固定 JSON，不把 query、retrieved text 或 secrets 傳進 n8n execution history。

**Tech Stack:** n8n 2.37.10 JSON workflow、Python 3.12 wrapper、PowerShell／Windows `cmd` 啟動通道、既有 `evaluate_knowledge_retrieval.py`、`generate_training_status_report.py`、pytest。

**Spec:** `docs/superpowers/specs/2026-11-02-n8n-training-evaluation-design.md`

## Global Constraints

- 工作流只能 `Manual Trigger`，本輪不得啟用 Schedule Trigger。
- n8n 是 optional；n8n 關閉時 5001 核心聊天與記憶路徑必須仍可用。
- 固定執行 wrapper 與固定 Python／工作區絕對路徑；不得接受任意 shell 命令或使用者輸入。
- `gate_passed` 必須同時符合 `health.required_ready`、`cases >= 30`、`hit_rate >= 0.75`、`privacy_leakage == 0`、`stale_retrieved == 0` 與 training readiness 四層全為 true。
- 失敗仍輸出固定 JSON 並設定 `gate_passed=false`；不得只留下模糊的 n8n execution failed。
- n8n execution history 只保存 aggregate metrics、run_id、artifact paths 與中文說明。
- 不做模型權重微調，不新增外部 API／credentials，不直接修改 n8n SQLite。

## Review Focus

- evaluator exit code 非 0 但舊的 `*_latest.json` 存在：測試不能把上一輪結果誤當本輪成功（Task 1）。
- health `required_ready=false`：工作流應停止後續訓練步驟並產生 `gate_passed=false`（Task 1、Task 3）。
- retrieval cases 不足 30、hit rate 低於 0.75、stale 或 privacy 非零：必須明確列出 gate 原因（Task 1）。
- evaluator 輸出含 query／per-case results：wrapper 與 n8n 最終輸出都只能保留 aggregate metadata（Task 1、Task 3）。
- Windows 路徑含空白、Python／n8n 啟動逾時或 workflow JSON 缺節點：匯入前要可診斷且不修改既有 workflow（Task 2、Task 4）。

---

### Task 1: 固定 wrapper 與 gate 契約

**Files:**
- Create: `tools/n8n_training_evaluation.py`
- Test: `tests/test_n8n_training_evaluation.py`

**Interfaces:**
- Produces `run_pipeline(repo_root, data_root, backup_root, retrieval_report, training_report, health_url, python_executable) -> dict[str, Any]`。
- CLI 無參數時使用工作區固定預設；n8n 命令列會明確傳入固定絕對路徑，不接受 n8n item data 插值。
- Payload 必含 `schema_version`、`run_id`、`gate_passed`、`intro_zh`、`summary_zh`、`health`、`retrieval`、`training`、`artifacts`、`errors`。

- [ ] **Step 1: Write failing tests**

建立測試替身，不呼叫真實 n8n：

1. health ready + evaluator／report 全通過 → `gate_passed is True`，payload 沒有 query／retrieved text。
2. health 不 ready → evaluator 不被呼叫，`errors` 有 `health_gate_failed`。
3. hit rate `< 0.75`、cases `< 30`、stale 或 privacy 非零 → `gate_passed is False`，每個原因都列出。
4. evaluator 非 0 且舊報告存在 → 不讀舊報告冒充成功。
5. evaluator 輸出含 `results`／query → 最終 payload 只保留 aggregate keys。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_n8n_training_evaluation.py`

Expected: FAIL because the wrapper and `run_pipeline` do not exist。

- [ ] **Step 3: Implement minimal wrapper**

在 `tools/n8n_training_evaluation.py` 實作：

- 以 `urllib` 讀取 health JSON；逾時、非 JSON、非 200 都轉成結構化 error。
- 以 `subprocess.run(..., cwd=repo_root, timeout=120, capture_output=True, text=True)` 呼叫既有 evaluator，再呼叫 status generator。
- evaluator 先寫入指定 temporary／latest report；只有 return code 為 0 且本輪 `generated_at`／run id 可對應時才採用。
- 只從報告讀取 aggregate metrics；不要把 evaluator stdout 的完整 JSON 放進返回 payload。
- 依 Global Constraints 計算 gate，中文 summary 明確指出失敗層級。
- 對 artifact 寫入使用原子替換，並把路徑限制在 `data_root`／`backup_root` 或 repo reports 範圍。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_n8n_training_evaluation.py`

Expected: all wrapper contract tests pass。

- [ ] **Step 5: Commit**

```bash
git add tools/n8n_training_evaluation.py tests/test_n8n_training_evaluation.py
git commit -m "feat: add n8n training evaluation wrapper"
```

### Task 2: 建立可驗證的 n8n workflow JSON

**Files:**
- Create: `automation/n8n/trevor-training-evaluation.json`
- Modify: `automation/n8n/README.md`
- Test: `tests/test_n8n_workflow_contract.py`

**Interfaces:**
- Workflow 名稱固定為 `Trevor Training Evaluation (Manual)`，`active=false`。
- Nodes 固定包含 `Manual Trigger`、`Read Trevor readiness`、`Health gate`、`Run fixed training evaluator`、`Sanitize result`。
- Execute Command node 只呼叫固定 wrapper 絕對路徑與固定參數；不讀 n8n item data。

- [ ] **Step 1: Write failing workflow contract tests**

測試 JSON：manual trigger 存在且是唯一 trigger、active 為 false、無 credentials／webhook／schedule、HTTP URL 僅為 localhost、Execute Command 不含任意 input interpolation、連線順序符合 health gate → wrapper → sanitize。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_n8n_workflow_contract.py`

Expected: FAIL because the new workflow JSON does not exist。

- [ ] **Step 3: Implement workflow JSON and README instructions**

以現有 `trevor-local-health-check.json` 的安全設定為基線，新增獨立 workflow。健康 gate 失敗時走固定 Code node 產生 `gate_passed=false` payload；成功時呼叫 wrapper，再由 Code node 只保留 aggregate keys。README 要寫明：手動匯入、手動執行、預期輸出、停止／回滾方式與不可直接啟用排程。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_n8n_workflow_contract.py`

Expected: all workflow contract tests pass。

- [ ] **Step 5: Commit**

```bash
git add automation/n8n/trevor-training-evaluation.json automation/n8n/README.md tests/test_n8n_workflow_contract.py
git commit -m "feat: add manual n8n training evaluation workflow"
```

### Task 3: 匯入前 validator 與本機 smoke test

**Files:**
- Create: `tools/validate_n8n_training_workflow.py`
- Create: `tools/smoke_test_n8n_training_evaluation.ps1`
- Test: `tests/test_n8n_workflow_import_contract.py`

**Interfaces:**
- `validate_n8n_training_workflow.py --workflow PATH` 回傳 0／非 0，檢查 schema、節點、連線、active 狀態、credentials 與 command allowlist。
- PowerShell smoke test 只在 5678／healthz ready 後執行，並以 bounded timeout 驗證 workflow JSON 可被 n8n import command 接受；不得無限等待。

- [ ] **Step 1: Write failing validator tests**

測試缺 manual trigger、active=true、外部 URL、credentials、非 allowlist command、缺節點與壞 JSON 時都會失敗；正確 workflow 通過。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_n8n_workflow_import_contract.py`

Expected: FAIL because validator and smoke script do not exist。

- [ ] **Step 3: Implement validator and bounded smoke script**

validator 先做純離線檢查；PowerShell 以 `Start-Process`／timeout 取得 import exit code，遇到 CLI 卡住時輸出診斷並停止，不重複啟動 n8n、不修改 SQLite。

- [ ] **Step 4: Run tests and local smoke test**

Run:

```powershell
python -m pytest -q tests/test_n8n_workflow_import_contract.py
powershell -ExecutionPolicy Bypass -File .\tools\smoke_test_n8n_training_evaluation.ps1
```

Expected: validator pass；smoke test 以 bounded timeout 完成並回報 import／healthz 狀態。

- [ ] **Step 5: Commit**

```bash
git add tools/validate_n8n_training_workflow.py tools/smoke_test_n8n_training_evaluation.ps1 tests/test_n8n_workflow_import_contract.py
git commit -m "test: add n8n workflow import smoke checks"
```

### Task 4: 端到端驗收與回歸

**Files:**
- Modify: `automation/n8n/README.md` (only if observed runtime differs)
- Test: existing full suite plus manual n8n execution evidence

**Interfaces:**
- n8n workflow execution output must match wrapper schema and contain no private content。
- Trevor `/health/ready` and `/chat_shell` remain available whether n8n is listening or stopped。

- [ ] **Step 1: Import one inactive workflow and verify SQLite count／name**

Confirm the database contains the new workflow without deleting or overwriting the baseline artifact。

- [ ] **Step 2: Run the workflow manually once**

Capture only status, run_id, gate, metrics and artifact paths; inspect that execution history does not contain query or retrieved text。

- [ ] **Step 3: Run focused tests**

Run: `python -m pytest -q tests/test_n8n_training_evaluation.py tests/test_n8n_workflow_contract.py tests/test_n8n_workflow_import_contract.py`

- [ ] **Step 4: Run full regression**

Run: `python -m pytest -q`

Expected: all existing tests plus new n8n tests pass; n8n remains optional in readiness。

- [ ] **Step 5: Regenerate the Chinese training status report and commit final documentation**

Verify `training_status_latest.json` has `readiness.*`, `intro_zh`, `summary_zh`, and `field_descriptions_zh`; report any optional TLS/OpenClaw gap separately from the core gate。

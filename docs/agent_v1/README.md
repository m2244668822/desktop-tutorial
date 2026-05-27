# Agent V1 (3/6/7/8) 實作說明

此版本重點：

- `3` 分層上下文：L0/L1/L2
- `6` 多代理協作：Planner/Router/Executor/Reviewer 交接格式
- `7` 評測先行：golden set + 自動評測
- `8` 可觀測性：trace + 指標聚合

## 1) TaskState Schema

- 檔案：`docs/agent_v1/task_state.schema.json`
- 核心欄位：`task_id`, `trace_id`, `overall_status`, `steps`, `observability`, `memory_write_allowed`

## 2) 交接協議 (handoff contract)

每一段交接都維持固定欄位：

- `goal`
- `inputs`
- `outputs`
- `risks`
- `next_action`

目前已在 `core/langgraph_workflow.py` 寫入 `state.collaboration.handoffs`。

## 3) L0/L1/L2 分層

`context_layers` 工具會回傳：

- `l0`: 最近會話摘要（短期）
- `l1`: 最近成功 workflow 任務（專案工作記憶）
- `l2`: 長期知識檢索（SQLite + FAISS）

並寫入 `task_state.memory_layers`。

## 4) 記憶寫入 Gate

僅當 preview 流程驗證成功時，才執行寫入型 action。

- `task_state.memory_write_allowed = true` 才代表可升級記憶
- 否則會保留 `memory_write_block_reason`

## 5) 評測

- 資料集：`evals/golden_set_v1.jsonl`
- 執行：

```bash
.venv312/bin/python tools/run_workflow_eval.py
```

輸出指標：

- `success_rate`
- `first_pass_rate`
- `manual_intervention_rate`
- `avg_step_count`
- `avg_duration_ms`

## 6) 可觀測性

- 執行：

```bash
.venv312/bin/python tools/workflow_observability_report.py --days 7 --limit 300
```

輸出：

- `reports/observability/latest.json`
- `reports/observability/latest.md`

內容含：

- 成功/失敗率
- error breakdown
- 失敗工具排行
- retry hotspots
- 最新失敗任務

## 7) Golden Set 擴充建議

目前已放 30 筆 golden case。
後續可擴充到 50+，並涵蓋：

- 低風險資訊整理
- 中風險查詢與路由
- 高風險修復與寫入

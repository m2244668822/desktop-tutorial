# inbox-executor（路 B）

常駐輪詢 [[chatgpt-inbox]]：`status: queued` 且有 **Mechanical Actions** JSON 時，呼叫同目錄旁的 `vault_workspace_mcp` 執行；否則 `blocked`，改由 Cursor。

**不是**第二套 Agent；只是 Perob `services/` 下的機械執行器。

## 啟動

```bat
runtime\啟動 inbox-executor.cmd
```

單次：

```bat
runtime\跑 inbox-executor-once.cmd
```

環境變數：

| 變數 | 預設 | 意思 |
|---|---|---|
| `VAULT_WORKSPACE_ROOT` | vault 根 | 工作區 |
| `INBOX_POLL_MS` | 5000 | 輪詢間隔 |
| `INBOX_AUTO_APPROVE` | 0 | `1`＝L2+ 自動核准（只在信任契約時開） |

## ChatGPT 必寫區塊

在 inbox 契約下方加：

````markdown
## Mechanical Actions

```json
{
  "executor": "inbox-daemon",
  "auto_approve": false,
  "actions": [
    { "tool": "workspace.read", "args": { "path": "00 圖書館總覽.md" } }
  ]
}
```
````

寫入類（patch／create）若 `auto_approve=false`，需在 args 帶 `approval`，或先被 daemon blocked 後用回傳的 `diff_hash`／`action_id` 再 queued 一次。

## Transport (GitHub sync)

`at
set INBOX_SYNC_PULL=1
set INBOX_SYNC_PUSH=0
node src/sync.js
`

Or: `runtime\跑 inbox-sync-once.cmd` / `runtime\啟動 inbox-sync-loop.cmd`.
Pushback requires `INBOX_SYNC_PUSH=1`.

## Executor Identity Contract

每次 `queued → running` 會先寫入 `Executor Claim`。Claim 與 Result 共用同一份 identity，至少包含：

- `executor_id`、`executor_type`、`executor_provider`、`executor_product`
- `executor_mode`、`executor_version`、`executor_capabilities`、`claimed_at`

目前執行者以主動宣告為準：可用 `INBOX_EXECUTOR_IDENTITY` JSON，或使用 `INBOX_EXECUTOR_*` 欄位。CLI／工具是否存在只代表 capability，不得推定為目前 executor。舊任務沒有 identity 欄位時仍可讀為 legacy；新 claim 與 Result 不一致則回傳 `executor_identity_mismatch`。

## Policy-governed transactional execution

目前的 durable queue 是 `智能體/tasks/*.md`。舊的
`智能體/chatgpt-inbox.md` 只有在明確設定
`WHITE_STUDIO_ALLOW_LEGACY_INBOX=1` 時才會被選取，避免兩個 checkout
同時執行同一份任務。

每次執行都建立：

- lease：`lease_id`、`lease_generation`、`fencing_token`、`executor_id`、到期與 heartbeat。
- operation journal：追加 `requested`、`authorized`、`executing`、`applied`、`validated`、`completed` 或失敗 transition。
- idempotency：相同 key 與 request replay 原結果；相同 key 搭配不同 request 回傳 `HARD_CONFLICT`。
- Result CAS：回寫前檢查 lease、executor identity 與被 claim 的 task blob revision。

`runtime/test-profiles.json` 的 `automation_mode` 控制 project：Primary Vault
為 `manual_only`；註冊的產品／Runtime project 才能進入 `bounded_write`。
canonical、frozen、secret pattern 仍被拒絕。`runtime/.mcp-state/` 只保存本機
狀態，不是 canonical source，也不會自動 promotion。

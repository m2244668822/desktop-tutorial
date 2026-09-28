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

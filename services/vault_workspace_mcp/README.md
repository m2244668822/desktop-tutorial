# vault-workspace-mcp（Perob 服務）

本目錄是 `desktop-tutorial` 內的 **Vault-scoped MCP 工具服務**，不是第二套 Agent。它由 VS Code／其他本機 MCP Host 以 **stdio** 啟動，工作範圍由 `VAULT_WORKSPACE_ROOT` 限制。

## 運行契約

```text
MCP Host
  │
  ├─ command: node
  ├─ args: src/server.js
  └─ env:
       VAULT_WORKSPACE_ROOT=<vault-root>
       MCP_AUTO_APPROVE=0
       MCP_FRAMING=newline
  │
  ▼
stdin/stdout = newline-delimited JSON-RPC
stderr       = logs only
  │
  ▼
vault-workspace-mcp
```

- 預設 framing：`newline`。
- `Content-Length` 只保留為 legacy explicit opt-in：`MCP_FRAMING=content-length`。
- stdout 不得輸出一般 log；診斷訊息只能走 stderr。
- `MCP_AUTO_APPROVE=0` 是預設安全邊界。

## 工作範圍

- `VAULT_WORKSPACE_ROOT`：Vault 根目錄。
- Internal tool IDs remain dotted for audit / Inbox compatibility: `workspace.read`, `runtime.capabilities`, etc.
- MCP Host-facing tool names use VS Code-compatible identifiers: `workspace_read`, `workspace_propose_patch`, `git_checkpoint`, `runtime_capabilities`, `runtime_run_test`, `trevor_web_search`, etc.
- The server translates host-safe underscore names back to the existing internal dotted IDs before dispatch.
- 寫入：proposal/diff → permission → approval → apply → audit。
- Audit：`runtime/.mcp-audit/mcp-audit.jsonl`。
- Trash：搬到 `runtime/.mcp-trash/`，不做永久刪除。

## 本機啟動

Windows CMD：

```bat
set VAULT_WORKSPACE_ROOT=<vault-root>
set MCP_AUTO_APPROVE=0
set MCP_FRAMING=newline
node src\server.js
```

PowerShell：

```powershell
$env:VAULT_WORKSPACE_ROOT="<vault-root>"
$env:MCP_AUTO_APPROVE="0"
$env:MCP_FRAMING="newline"
node .\src\server.js
```

通常不需要手動啟動；MCP Host 應直接 spawn `node src/server.js`。

## VS Code Host 範例

Host 設定應放在實際工作區 repo，例如主 Vault 的 `.vscode/mcp.json`：

```json
{
  "servers": {
    "vault-workspace": {
      "type": "stdio",
      "command": "node",
      "args": [
        "${workspaceFolder}/runtime/desktop-tutorial/services/vault_workspace_mcp/src/server.js"
      ],
      "env": {
        "VAULT_WORKSPACE_ROOT": "${workspaceFolder}",
        "MCP_AUTO_APPROVE": "0",
        "MCP_FRAMING": "newline"
      }
    }
  }
}
```

這個 Runtime repo 不保存使用者 Vault 的絕對路徑或 credential。

## 驗收

執行：

```bash
npm run e2e
```

成功至少要同時看到：

```text
STDIO_HANDSHAKE_PASS
E2E_PASS
```

E2E 涵蓋：

1. 真實 `initialize` handshake。
2. `notifications/initialized`。
3. `tools/list`，且所有公開 tool names 符合 `[A-Za-z0-9_-]+`。
4. Host-safe `runtime_capabilities` 可經真實 `tools/call` dispatch 成功。
5. Internal `workspace.read`。
6. bounded `runtime.run_test`。
7. propose patch → approval → apply → verify → rollback。
7. audit 產生。

只有 server process 存在、Host 顯示 server 名稱或歷史 E2E 通過，都不能單獨視為「目前 MCP online」。

## 故障定位

```text
Host config
  ↓
process spawn
  ↓
initialize
  ↓
tools/list
  ↓
workspace_read (Host)
→ workspace.read (internal dispatch)
  ↓
write/approval/audit
```

- spawn 前失敗：查 Node PATH、Host config、server.js 路徑。
- initialize 失敗：查 framing、stdout 汙染、JSON-RPC。
- tools/list 失敗：查 protocol/tool schema。
- tools/list PASS 但 read FAIL：查 Vault root、path、permission。
- E2E PASS 但 VS Code FAIL：問題縮到 Host cache/lifecycle/Windows process 層。

## Parent submodule 規則

主 Vault 以 Git submodule 固定本 Runtime 的 commit。child `main` 更新 **不代表** parent 已使用新版。

驗收要同時確認：

```bash
git ls-tree HEAD runtime/desktop-tutorial
git -C runtime/desktop-tutorial rev-parse HEAD
```

兩個 SHA 必須一致。

## 安全邊界

- 不提供 unrestricted shell。
- 寫入需經 permission/approval。
- 所有目標路徑受 `VAULT_WORKSPACE_ROOT` 限制。
- 不把本機 stdio server 直接暴露到公網。
- 不把金鑰、token 或私人 Vault 絕對路徑提交到 repo。

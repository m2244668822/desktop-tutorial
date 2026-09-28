# vault-workspace-mcp（Perob 服務）

本目錄是 **desktop-tutorial 內的 MCP 檔案工具服務**，不是第二套 Agent。

## 範圍

- `VAULT_WORKSPACE_ROOT`：預設為本 Obsidian vault 根目錄
- Tools：`workspace.list|search|read|create|patch|move|trash`、`git.checkpoint`
- 寫入：diff → permission → approval → apply → audit（`.mcp-audit/mcp-audit.jsonl`）
- trash：搬到 `runtime/.mcp-trash/`，無永久刪除

## 啟動（stdio MCP）

```bash
cd runtime/desktop-tutorial/services/vault_workspace_mcp
set VAULT_WORKSPACE_ROOT=<vault-root>
set MCP_AUTO_APPROVE=0
node src/server.js
```

E2E（本機驗收）：

```bash
npm run e2e
```

## ChatGPT Web

Plus／個人版通常無法 Secure Tunnel 直控寫檔。日常走 vault 內 `chatgpt-inbox`；本服務供 Cursor／本機 Executor 呼叫。升級 Business＋Developer Mode 後，再用 Tunnel 掛此 stdio／HTTP 邊界。

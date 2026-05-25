# Cursor Agent Sidebar

A local Cursor/VS Code extension sidebar for:

- direct agent chat (`POST /chat/agent`)
- backend-style live request status while chatting
- async full sync trigger (`POST /sync`, `type=full_sync`, `async=true`)
- full sync progress query (`GET /sync/full-sync/jobs`, `GET /sync/full-sync/jobs/<job_id>`)
- bridge, trace, reality board, and learning metric checks

## Prerequisites

- Backend server running: `chatgpt_server.py` on `http://127.0.0.1:5001`
- `SERVER_API_TOKEN` configured (if `SERVER_API_TOKEN_REQUIRED=true`)

## Run in development

1. Open this extension folder in Cursor: `cursor-agent-sidebar-extension`.
2. Press `F5` (or run `Debug: Start Debugging`) to launch Extension Development Host.
3. In the new host window, click Activity Bar icon `Agent Hub`.
4. Fill `baseUrl` and `serverToken` then click `Health`.

## Install as VSIX (optional)

1. Install Node.js and `vsce`.
2. Run:

   ```bash
   npm install -g @vscode/vsce
   vsce package
   ```

3. In Cursor: `Extensions: Install from VSIX...` and pick generated `.vsix`.

## Notes

- If `/sync` returns `403`, check `Authorization: Bearer <SERVER_API_TOKEN>`.
- If `/sync` returns `503`, check server-side fail-closed config and token requirements.
- The sidebar is designed as a backend console plus chat surface: every API call updates the live backend panel with endpoint, HTTP status, latency, and timestamp.

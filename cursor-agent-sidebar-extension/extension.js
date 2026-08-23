// @ts-nocheck
const vscode = require('vscode');

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

class AgentSidebarProvider {
  constructor(extensionUri) {
    this.extensionUri = extensionUri;
    this.view = undefined;
    this.outputChannel = vscode.window.createOutputChannel('智能體側欄');
    this.replyTerminal = undefined;
  }

  dispose() {
    if (this.replyTerminal) {
      try {
        this.replyTerminal.dispose();
      } catch (_) {}
      this.replyTerminal = undefined;
    }
    if (this.outputChannel) {
      try {
        this.outputChannel.dispose();
      } catch (_) {}
      this.outputChannel = undefined;
    }
  }

  _ensureReplyTerminal() {
    if (this.replyTerminal && !this.replyTerminal.exitStatus) {
      return this.replyTerminal;
    }
    this.replyTerminal = vscode.window.createTerminal({
      name: '智能體回覆終端機',
      hideFromUser: false,
    });
    return this.replyTerminal;
  }

  _shellQuote(text) {
    return "'" + String(text || '').replace(/'/g, "'\"'\"'") + "'";
  }

  _writeReplyToTerminal(text) {
    const raw = String(text || '').replace(/\r\n/g, '\n');
    if (!raw.trim()) {
      return;
    }
    const lines = raw.split('\n').slice(0, 120);
    const payload = lines.map((line) => this._shellQuote(line)).join(' ');
    if (!payload) {
      return;
    }
    const terminal = this._ensureReplyTerminal();
    terminal.show(true);
    terminal.sendText(`printf '%s\\n' ${payload}`, true);
  }

  resolveWebviewView(webviewView) {
    this.view = webviewView;
    const config = vscode.workspace.getConfiguration('cursorAgentSidebar');
    const serverBaseUrl = config.get('serverBaseUrl', 'http://127.0.0.1:5001');
    const serverToken = config.get('serverToken', '');
    const bridgeToken = config.get('bridgeToken', '');

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.getHtml(webviewView.webview, {
      serverBaseUrl,
      serverToken,
      bridgeToken,
    });

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (!msg || typeof msg !== 'object') {
        return;
      }

      if (msg.type === 'saveConfig') {
        const payload = msg.payload || {};
        await vscode.workspace.getConfiguration('cursorAgentSidebar').update(
          'serverBaseUrl',
          String(payload.serverBaseUrl || '').trim() || 'http://127.0.0.1:5001',
          vscode.ConfigurationTarget.Workspace,
        );
        await vscode.workspace.getConfiguration('cursorAgentSidebar').update(
          'serverToken',
          String(payload.serverToken || '').trim(),
          vscode.ConfigurationTarget.Workspace,
        );
        await vscode.workspace.getConfiguration('cursorAgentSidebar').update(
          'bridgeToken',
          String(payload.bridgeToken || '').trim(),
          vscode.ConfigurationTarget.Workspace,
        );

        vscode.window.showInformationMessage('側欄設定已儲存。');
        return;
      }

      if (msg.type === 'terminalLog') {
        const payload = msg.payload || {};
        const text = String(payload.text || payload.line || '').trim();
        if (!text) {
          return;
        }
        if (this.outputChannel) {
          this.outputChannel.appendLine(text);
        }
        this._writeReplyToTerminal(text);
      }
    });
  }

  getHtml(webview, initialConfig) {
    const nonce = String(Date.now());
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, 'media', 'sidebar.js'),
    );
    const initialConfigBase64 = Buffer.from(
      JSON.stringify(initialConfig),
      'utf8',
    ).toString('base64');

    return `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} https: data:; style-src 'unsafe-inline'; script-src ${webview.cspSource} 'nonce-${nonce}'; connect-src *;" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>智能體側欄</title>
  <style>
    :root {
      color-scheme: dark;
      --bg-main: #060a10;
      --bg-grad-a: #0b1523;
      --bg-grad-b: #0d1017;
      --card-bg: rgba(10, 15, 24, 0.86);
      --card-border: rgba(148, 163, 184, 0.28);
      --subcard-bg: rgba(30, 41, 59, 0.35);
      --text-main: #e6edf6;
      --text-soft: #a8b5c7;
      --text-faint: #8b9bb2;
      --focus: #35b6ff;
      --primary: #18a6ee;
      --primary-border: #0284c7;
      --control-bg: rgba(148, 163, 184, 0.26);
      --ok: #22c55e;
      --warn: #f59e0b;
      --error: #ef4444;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 10px;
      font-family: "Noto Sans TC", "PingFang TC", "SF Pro Text", "Segoe UI", sans-serif;
      color: var(--text-main);
      background:
        radial-gradient(circle at 15% -10%, #12365d 0%, transparent 46%),
        radial-gradient(circle at 95% 0%, #1a2336 0%, transparent 38%),
        linear-gradient(165deg, var(--bg-grad-a) 0%, var(--bg-grad-b) 62%, var(--bg-main) 100%);
    }

    .app-shell { display: flex; flex-direction: column; gap: 12px; }
    .topbar {
      padding: 8px 6px 4px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.28);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .eyebrow {
      margin: 0;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-faint);
    }
    .topbar h2 {
      margin: 0;
      font-size: 34px;
      line-height: 1.05;
      font-weight: 760;
      letter-spacing: 0.01em;
    }
    .status-pills {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .pill {
      border: 1px solid rgba(148, 163, 184, 0.35);
      background: rgba(148, 163, 184, 0.16);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 11px;
      color: var(--text-soft);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .pill.ok { border-color: rgba(34, 197, 94, 0.5); color: #86efac; background: rgba(34, 197, 94, 0.15); }
    .pill.warn { border-color: rgba(245, 158, 11, 0.5); color: #fde68a; background: rgba(245, 158, 11, 0.15); }
    .pill.error { border-color: rgba(239, 68, 68, 0.55); color: #fecaca; background: rgba(239, 68, 68, 0.16); }

    .backend-live {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .backend-row {
      display: grid;
      grid-template-columns: 88px minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      border: 1px solid rgba(148, 163, 184, 0.22);
      background: rgba(2, 8, 20, 0.3);
      border-radius: 8px;
      padding: 8px;
      min-height: 36px;
    }
    .backend-label {
      color: var(--text-faint);
      font-size: 11px;
      line-height: 1.35;
    }
    .backend-value {
      color: var(--text-main);
      font-size: 11px;
      line-height: 1.45;
      word-break: break-word;
    }
    .backend-value.ok { color: #86efac; }
    .backend-value.warn { color: #fde68a; }
    .backend-value.error { color: #fecaca; }
    .command-note {
      border-left: 3px solid rgba(53, 182, 255, 0.8);
      background: rgba(14, 165, 233, 0.1);
      border-radius: 8px;
      padding: 8px 10px;
      color: var(--text-soft);
      font-size: 11px;
      line-height: 1.45;
      margin-bottom: 8px;
    }

    .card {
      border: 1px solid var(--card-border);
      background: var(--card-bg);
      border-radius: 14px;
      padding: 12px;
      box-shadow: 0 14px 30px rgba(2, 8, 20, 0.36), inset 0 1px 0 rgba(255, 255, 255, 0.04);
      animation: card-in 0.32s ease-out both;
    }
    .card h3 {
      margin: 0 0 10px;
      font-size: 14px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--text-soft);
    }
    .subcard {
      border: 1px solid rgba(148, 163, 184, 0.24);
      background: var(--subcard-bg);
      border-radius: 10px;
      padding: 9px;
      margin-bottom: 8px;
    }
    .subcard:last-child { margin-bottom: 0; }
    .subcard h4 {
      margin: 0 0 8px;
      font-size: 12px;
      color: var(--text-main);
      font-weight: 640;
    }

    .row { display: flex; gap: 8px; margin-bottom: 8px; }
    .row:last-child { margin-bottom: 0; }
    .row.two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .row.token-row { align-items: center; }

    input, select, textarea, button {
      width: 100%;
      font: inherit;
      color: var(--text-main);
    }
    input, select, textarea {
      border-radius: 10px;
      border: 1px solid rgba(148, 163, 184, 0.4);
      background: rgba(148, 163, 184, 0.24);
      padding: 10px 12px;
      min-height: 42px;
      outline: none;
      transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
    }
    input::placeholder, textarea::placeholder { color: var(--text-faint); }
    input:focus, select:focus, textarea:focus {
      border-color: rgba(53, 182, 255, 0.88);
      box-shadow: 0 0 0 3px rgba(53, 182, 255, 0.2);
      background: rgba(148, 163, 184, 0.3);
    }
    textarea {
      min-height: 108px;
      resize: vertical;
      line-height: 1.45;
    }

    button {
      border-radius: 10px;
      border: 1px solid rgba(148, 163, 184, 0.45);
      background: var(--control-bg);
      min-height: 42px;
      padding: 9px 10px;
      cursor: pointer;
      font-weight: 640;
      transition: transform .08s ease, filter .15s ease, border-color .15s ease;
    }
    button:hover { filter: brightness(1.06); }
    button:active { transform: translateY(1px); }
    button.primary {
      background: linear-gradient(180deg, #25b1f4 0%, var(--primary) 100%);
      border-color: var(--primary-border);
      color: #f7fbff;
    }
    button.ghost {
      width: auto;
      min-width: 72px;
      padding-inline: 11px;
      background: rgba(2, 132, 199, 0.12);
      border-color: rgba(56, 189, 248, 0.5);
      color: #7dd3fc;
    }
    button.mini {
      min-height: 38px;
      border-radius: 9px;
      font-size: 12px;
    }

    .mono {
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 11px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
    }
    .hint { font-size: 11px; color: var(--text-faint); line-height: 1.45; }
    .status { font-size: 12px; margin-top: 6px; color: var(--text-soft); }
    .agent-reply-panel {
      margin-top: 8px;
      border-radius: 10px;
      border: 1px solid rgba(59, 130, 246, 0.35);
      background: rgba(15, 23, 42, 0.46);
      padding: 10px;
    }
    .agent-reply-meta {
      font-size: 11px;
      color: var(--text-faint);
      margin-bottom: 6px;
      line-height: 1.5;
    }
    .agent-reply-body {
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--text-main);
      min-height: 18px;
    }
    .agent-reply-body.error {
      color: #fecaca;
    }
    .reality-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }
    .reality-card {
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 10px;
      padding: 8px;
      background: rgba(15, 23, 42, 0.45);
      display: flex;
      gap: 8px;
      align-items: flex-start;
      min-height: 88px;
    }
    .reality-card.running {
      border-color: rgba(34, 197, 94, 0.55);
      box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    }
    .reality-card.pending {
      border-color: rgba(245, 158, 11, 0.52);
    }
    .reality-card.failed {
      border-color: rgba(239, 68, 68, 0.58);
    }
    .reality-body {
      min-width: 0;
      flex: 1;
    }
    .reality-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
    }
    .reality-name {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.3;
    }
    .reality-name-wrap {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }
    .state-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.45);
      background: rgba(148, 163, 184, 0.4);
      flex: 0 0 auto;
    }
    .state-dot.running {
      background: #22c55e;
      border-color: rgba(134, 239, 172, 0.85);
      box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.55);
      animation: state-pulse-running 1.8s ease-out infinite;
    }
    .state-dot.pending {
      background: #f59e0b;
      border-color: rgba(253, 230, 138, 0.8);
      box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.45);
      animation: state-pulse-pending 2s ease-out infinite;
    }
    .state-dot.failed {
      background: #ef4444;
      border-color: rgba(254, 202, 202, 0.8);
    }
    .state-dot.idle {
      background: #64748b;
      border-color: rgba(203, 213, 225, 0.72);
    }
    .reality-state {
      font-size: 10px;
      border-radius: 999px;
      padding: 1px 8px;
      border: 1px solid rgba(148, 163, 184, 0.38);
      background: rgba(148, 163, 184, 0.18);
      color: var(--text-soft);
      white-space: nowrap;
    }
    .reality-state.running {
      border-color: rgba(34, 197, 94, 0.55);
      background: rgba(34, 197, 94, 0.18);
      color: #bbf7d0;
    }
    .reality-state.pending {
      border-color: rgba(245, 158, 11, 0.5);
      background: rgba(245, 158, 11, 0.16);
      color: #fde68a;
    }
    .reality-state.idle {
      border-color: rgba(148, 163, 184, 0.42);
      background: rgba(148, 163, 184, 0.16);
      color: #cbd5e1;
    }
    .reality-state.failed {
      border-color: rgba(239, 68, 68, 0.56);
      background: rgba(239, 68, 68, 0.18);
      color: #fecaca;
    }
    .reality-task {
      font-size: 11px;
      color: var(--text-soft);
      line-height: 1.45;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .reality-meta {
      margin-top: 6px;
      font-size: 10px;
      color: var(--text-faint);
      line-height: 1.4;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    .reality-kpi {
      border: 1px solid rgba(148, 163, 184, 0.28);
      background: rgba(2, 8, 20, 0.52);
      border-radius: 999px;
      padding: 1px 7px;
      white-space: nowrap;
    }
    .reality-kpi strong {
      color: var(--text-main);
      font-weight: 700;
    }
    .semantic-trend-panel {
      margin-top: 8px;
      border: 1px solid rgba(125, 211, 252, 0.24);
      border-radius: 10px;
      background: rgba(8, 16, 30, 0.62);
      padding: 8px;
      font-size: 11px;
      line-height: 1.45;
      color: var(--text-soft);
    }
    .language-monitor-panel {
      margin-top: 8px;
      border: 1px solid rgba(74, 222, 128, 0.24);
      border-radius: 10px;
      background: rgba(6, 16, 22, 0.72);
      padding: 8px;
      font-size: 11px;
      line-height: 1.45;
      color: var(--text-soft);
    }
    .language-monitor-grid {
      margin-top: 6px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .language-chip {
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.55);
      padding: 5px 6px;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .language-chip .label {
      color: var(--text-faint);
      font-size: 10px;
    }
    .language-chip .value {
      color: var(--text-main);
      font-size: 11px;
      font-weight: 700;
    }
    .language-chip.ok { border-color: rgba(34, 197, 94, 0.45); }
    .language-chip.warning { border-color: rgba(245, 158, 11, 0.48); }
    .language-chip.no_data { border-color: rgba(148, 163, 184, 0.35); }
    .agent-avatar {
      width: 48px;
      height: 48px;
      min-width: 48px;
      min-height: 48px;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.35);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.25),
        0 8px 20px rgba(2, 6, 23, 0.35);
    }
    .agent-avatar::before {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(140deg, rgba(255, 255, 255, 0.26) 0%, rgba(255, 255, 255, 0.04) 42%, rgba(255, 255, 255, 0) 70%);
      pointer-events: none;
    }
    .agent-avatar-glyph {
      position: relative;
      z-index: 1;
      font-size: 17px;
      font-weight: 800;
      letter-spacing: 0.02em;
      color: #f8fbff;
      text-shadow: 0 1px 2px rgba(2, 6, 23, 0.4);
    }
    .agent-avatar.running {
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.25),
        0 0 0 0 rgba(34, 197, 94, 0.45),
        0 8px 20px rgba(2, 6, 23, 0.35);
      animation: avatar-pulse-running 1.8s ease-out infinite;
    }
    .agent-avatar.pending {
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.22),
        0 0 0 0 rgba(245, 158, 11, 0.38),
        0 8px 20px rgba(2, 6, 23, 0.35);
      animation: avatar-pulse-pending 2.2s ease-out infinite;
    }
    .agent-avatar.failed {
      border-color: rgba(239, 68, 68, 0.62);
    }
    .agent-avatar.theme-dispatcher { background: linear-gradient(145deg, #0f172a 0%, #0ea5e9 58%, #67e8f9 100%); }
    .agent-avatar.theme-engineer { background: linear-gradient(145deg, #0f172a 0%, #2563eb 55%, #93c5fd 100%); }
    .agent-avatar.theme-researcher { background: linear-gradient(145deg, #082f49 0%, #16a34a 55%, #86efac 100%); }
    .agent-avatar.theme-xiaobian { background: linear-gradient(145deg, #312e81 0%, #f59e0b 55%, #fde68a 100%); }
    .agent-avatar.theme-whitehat { background: linear-gradient(145deg, #111827 0%, #dc2626 55%, #fca5a5 100%); }
    .agent-avatar.theme-proclaimer { background: linear-gradient(145deg, #1f2937 0%, #7c3aed 55%, #ddd6fe 100%); }
    .agent-avatar.theme-learner { background: linear-gradient(145deg, #064e3b 0%, #0ea5a4 55%, #6ee7b7 100%); }
    .agent-avatar.theme-general { background: linear-gradient(145deg, #1e293b 0%, #475569 58%, #cbd5e1 100%); }
    .output-log {
      max-height: 240px;
      overflow: auto;
      border-radius: 10px;
      border: 1px solid rgba(148, 163, 184, 0.25);
      background: rgba(2, 8, 20, 0.45);
      padding: 9px;
    }

    @keyframes card-in {
      from { transform: translateY(6px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
    @keyframes state-pulse-running {
      0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5); }
      70% { box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }
      100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
    }
    @keyframes state-pulse-pending {
      0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.45); }
      70% { box-shadow: 0 0 0 7px rgba(245, 158, 11, 0); }
      100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
    }
    @keyframes avatar-pulse-running {
      0% { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 0 0 0 rgba(34, 197, 94, 0.42), 0 8px 20px rgba(2, 6, 23, 0.35); }
      70% { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 0 0 10px rgba(34, 197, 94, 0), 0 8px 20px rgba(2, 6, 23, 0.35); }
      100% { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 0 0 0 rgba(34, 197, 94, 0), 0 8px 20px rgba(2, 6, 23, 0.35); }
    }
    @keyframes avatar-pulse-pending {
      0% { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 0 0 0 rgba(245, 158, 11, 0.36), 0 8px 20px rgba(2, 6, 23, 0.35); }
      70% { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 0 0 9px rgba(245, 158, 11, 0), 0 8px 20px rgba(2, 6, 23, 0.35); }
      100% { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 0 0 0 rgba(245, 158, 11, 0), 0 8px 20px rgba(2, 6, 23, 0.35); }
    }

    .agent-network-wrap {
      margin-top: 8px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 10px;
      background: rgba(2, 8, 20, 0.45);
      overflow: hidden;
    }
    .agent-network-wrap svg { display: block; width: 100%; }
    @keyframes net-pulse-running {
      0%, 100% { stroke-opacity: 1; fill-opacity: 0.3; }
      50% { stroke-opacity: 0.25; fill-opacity: 0.08; }
    }
    @keyframes net-pulse-pending {
      0%, 100% { stroke-opacity: 0.85; fill-opacity: 0.22; }
      50% { stroke-opacity: 0.2; fill-opacity: 0.06; }
    }
    .net-node-running { animation: net-pulse-running 1.6s ease-in-out infinite; }
    .net-node-pending { animation: net-pulse-pending 2.0s ease-in-out infinite; }

    @media (max-width: 520px) {
      .status-pills { grid-template-columns: 1fr; }
      .row.two { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <meta id="cursor-agent-sidebar-config" data-base64="${escapeHtml(initialConfigBase64)}" />
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Agent Workshop</p>
        <h2>智能體控制台</h2>
      </div>
      <div class="status-pills">
        <span id="healthPill" class="pill">服務：未檢查</span>
        <span id="transportPill" class="pill">雲端：未檢查</span>
      </div>
    </header>

    <div class="card">
      <h3>連線設定</h3>
      <div class="row"><input id="baseUrl" placeholder="http://127.0.0.1:5001" /></div>
      <div class="row token-row">
        <input id="serverToken" type="password" placeholder="SERVER_API_TOKEN" autocomplete="off" />
        <button id="toggleServerToken" class="ghost mini" type="button">顯示</button>
      </div>
      <div class="row token-row">
        <input id="bridgeToken" type="password" placeholder="CHATGPT_BRIDGE_INGEST_TOKEN（選填）" autocomplete="off" />
        <button id="toggleBridgeToken" class="ghost mini" type="button">顯示</button>
      </div>
      <div class="row two">
        <button id="saveConfig">儲存設定</button>
        <button id="checkHealth">健康檢查</button>
      </div>
      <div id="healthStatus" class="status hint"></div>
    </div>

    <div class="card">
      <h3>後端實況</h3>
      <div class="backend-live">
        <div class="backend-row">
          <div class="backend-label">狀態</div>
          <div id="backendState" class="backend-value warn">等待後端請求。</div>
        </div>
        <div class="backend-row">
          <div class="backend-label">Endpoint</div>
          <div id="backendEndpoint" class="backend-value mono">尚未呼叫。</div>
        </div>
        <div class="backend-row">
          <div class="backend-label">回應</div>
          <div id="backendResponse" class="backend-value mono">HTTP - | - ms</div>
        </div>
        <div class="backend-row">
          <div class="backend-label">更新</div>
          <div id="backendUpdated" class="backend-value mono">-</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>後端對話命令</h3>
      <div class="command-note">訊息會送到 POST /chat/agent；下方回覆區顯示智能體回應，上方後端實況同步顯示請求路徑、狀態碼與耗時。</div>
      <div class="row two">
        <select id="agent">
          <option value="general">general（通用）</option>
          <option value="dispatcher">dispatcher（總管）</option>
          <option value="engineer">engineer（工程）</option>
          <option value="researcher">researcher（研究）</option>
          <option value="whitehat">whitehat（白帽）</option>
          <option value="proclaimer">proclaimer（申言）</option>
          <option value="learner">learner（學習）</option>
          <option value="xiaobian">xiaobian（小編）</option>
        </select>
        <select id="model">
          <option value="auto">自動（雲端優先）</option>
          <option value="gemini">gemini</option>
          <option value="openai">openai</option>
          <option value="openrouter">openrouter</option>
          <option value="groq">groq</option>
          <option value="zhizengzeng">zhizengzeng</option>
          <option value="nvidia">nvidia</option>
        </select>
      </div>
      <div class="row"><textarea id="message" placeholder="輸入要傳給智能體的訊息..."></textarea></div>
      <div class="row"><button id="sendAgent" class="primary">送出</button></div>
      <div id="agentReplyPanel" class="agent-reply-panel">
        <div id="agentReplyMeta" class="agent-reply-meta">尚未送出訊息。</div>
        <div id="agentReplyBody" class="agent-reply-body">回覆會顯示在這裡。</div>
      </div>
    </div>

    <div class="card">
      <h3>實境面板</h3>
      <div class="hint">馬賽克角色即時顯示每個智能體現在正在做什麼。</div>
      <div id="realityBoard" class="reality-grid">
        <div class="hint">載入中...</div>
      </div>
      <div id="semanticTrendPanel" class="semantic-trend-panel mono hint">語言比對趨勢載入中...</div>
      <div id="languageMonitorPanel" class="language-monitor-panel mono hint">語言監控指標載入中...</div>
    </div>

    <div class="card">
      <h3>智能體網狀圖</h3>
      <div class="hint">節點 = 智能體 ｜ 連線 = 資料流向 ｜ 顏色閃爍 = 運作狀態</div>
      <div class="agent-network-wrap">
        <svg id="agentNetwork" viewBox="0 0 300 290" height="290" aria-label="智能體網狀圖"></svg>
      </div>
    </div>

    <div class="card">
      <h3>同步工作</h3>
      <div class="subcard">
        <h4>全量同步</h4>
        <div class="row two">
          <button id="startSync" class="primary">啟動非阻塞全量同步</button>
          <button id="listJobs">查看任務列表</button>
        </div>
        <div class="row"><input id="jobId" placeholder="任務 ID（job_id）" /></div>
        <div class="row two">
          <button id="pollJob">查詢任務狀態</button>
          <button id="toggleAutoPoll">自動輪詢：關閉</button>
        </div>
        <div class="hint">POST /sync（type=full_sync, async=true）+ GET /sync/full-sync/jobs/*</div>
      </div>
      <div class="subcard">
        <h4>半全量同步</h4>
        <div class="row two">
          <button id="startSemiSync">啟動非阻塞半全量同步</button>
          <button id="listSemiJobs">查看半全量任務</button>
        </div>
        <div class="row"><input id="semiJobId" placeholder="半全量任務 ID（job_id）" /></div>
        <div class="row two">
          <button id="pollSemiJob">查詢半全量任務</button>
          <button id="toggleSemiAutoPoll">自動輪詢：關閉</button>
        </div>
        <div class="hint">POST /sync（type=semi_full_sync, async=true）+ GET /sync/semi-full-sync/jobs/*</div>
      </div>
    </div>

    <div class="card">
      <h3>雲端對接驗證</h3>
      <div class="row two">
        <button id="checkTransport" class="primary">檢查雲端對接</button>
        <button id="toggleTransportPoll">自動檢查：關閉</button>
      </div>
      <div id="tracePanel" class="mono hint">Trace 尚未載入。</div>
      <div id="transportSummary" class="status hint">尚未檢查。</div>
      <div id="transportDetails" class="mono hint"></div>
    </div>

    <div class="card">
      <h3>橋接控制</h3>
      <div class="row two">
        <input id="controlInterval" type="number" min="60" max="86400" placeholder="最小間隔秒數（60+）" />
        <input id="controlMaxItems" type="number" min="5" max="60" placeholder="每次樣本數（5-60）" />
      </div>
      <div class="row two">
        <button id="pauseBridge">暫停</button>
        <button id="resumeBridge">恢復</button>
      </div>
      <div class="row two">
        <button id="applyBridgeControl">套用</button>
        <button id="resetBridgeCooldown">重置冷卻</button>
      </div>
      <div id="controlStatus" class="status hint">尚未讀取控制狀態。</div>
    </div>

    <div class="card">
      <h3>Learning 指標</h3>
      <div class="row"><button id="refreshMetrics">刷新指標</button></div>
      <div id="metricsPanel" class="mono hint">尚未載入 Learning 指標。</div>
    </div>

    <div class="card">
      <h3>輸出紀錄</h3>
      <div id="output" class="mono output-log">系統就緒。</div>
    </div>
  </div>

  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
}

function activate(context) {
  const provider = new AgentSidebarProvider(context.extensionUri);
  context.subscriptions.push(provider);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('cursorAgentSidebar.view', provider, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('cursorAgentSidebar.focus', async () => {
      await vscode.commands.executeCommand('workbench.view.extension.cursorAgentSidebar');
    }),
  );
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};

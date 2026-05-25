// @ts-nocheck
(() => {
  const vscode = acquireVsCodeApi();
  let autoPollTimer = null;
  let semiAutoPollTimer = null;
  let transportPollTimer = null;
  let latestTraceTimer = null;
  let metricsTimer = null;
  let realityTimer = null;
  const MAX_OUTPUT_LOG_LINES = 300;
  const TRACE_POLL_MS = 4000;
  const METRICS_POLL_MS = 12000;
  const TRANSPORT_POLL_MS = 15000;
  const REALITY_POLL_MS = 15000;
  const REALITY_FAILED_WINDOW_HOURS = 8;
  const SEMANTIC_TREND_DAYS = 7;
  const DEFAULT_API_TIMEOUT_MS = 30000;
  const CHAT_API_TIMEOUT_MS = 120000;
  const SYNC_API_TIMEOUT_MS = 180000;
  const REALITY_API_TIMEOUT_MS = 45000;
  const REALITY_AGENTS_ORDER = [
    "dispatcher",
    "engineer",
    "researcher",
    "xiaobian",
    "whitehat",
    "proclaimer",
    "general",
  ];
  const REALITY_AGENT_LABEL = {
    dispatcher: "總管",
    engineer: "工程師",
    researcher: "研究學習中樞",
    xiaobian: "小編",
    whitehat: "白帽",
    proclaimer: "申言者",
    general: "通用",
  };
  const REALITY_STATE_LABEL = {
    running: "進行中",
    pending: "待處理",
    failed: "阻塞",
    idle: "待命",
  };
  const DEFAULT_REPLY_META = "尚未送出訊息。";
  const DEFAULT_REPLY_BODY = "回覆會顯示在這裡。";
  let realityLoadInFlight = false;
  let realityLastError = "";
  let restoringUiState = false;

  const $ = (id) => document.getElementById(id);
  const output = $("output");

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function postTerminalLog(line) {
    const text = String(line || "").trim();
    if (!text) {
      return;
    }
    try {
      vscode.postMessage({
        type: "terminalLog",
        payload: { text },
      });
    } catch (_) {}
  }

  function decodeInitialConfig() {
    const defaults = {
      serverBaseUrl: "http://127.0.0.1:5001",
      serverToken: "",
      bridgeToken: "",
    };
    const meta = $("cursor-agent-sidebar-config");
    if (!meta) {
      return defaults;
    }
    const encoded = String(meta.dataset.base64 || "").trim();
    if (!encoded) {
      return defaults;
    }

    try {
      const jsonText = atob(encoded);
      const parsed = JSON.parse(jsonText);
      return {
        serverBaseUrl: String(parsed.serverBaseUrl || defaults.serverBaseUrl),
        serverToken: String(parsed.serverToken || ""),
        bridgeToken: String(parsed.bridgeToken || ""),
      };
    } catch (err) {
      return defaults;
    }
  }

  function hydrateInitialConfig() {
    const initial = decodeInitialConfig();
    $("baseUrl").value = initial.serverBaseUrl;
    $("serverToken").value = initial.serverToken;
    $("bridgeToken").value = initial.bridgeToken;
  }

  function logLine(line) {
    const ts = new Date().toISOString();
    const next = "[" + ts + "] " + line + "\n" + output.textContent;
    const lines = next.split("\n");
    if (lines.length > MAX_OUTPUT_LOG_LINES) {
      lines.length = MAX_OUTPUT_LOG_LINES;
    }
    output.textContent = lines.join("\n");
    persistUiState();
  }

  function getConfig() {
    return {
      baseUrl: ($("baseUrl").value || "").trim().replace(/\/$/, ""),
      serverToken: ($("serverToken").value || "").trim(),
      bridgeToken: ($("bridgeToken").value || "").trim(),
    };
  }

  function readPersistedUiState() {
    try {
      const state = vscode.getState();
      return state && typeof state === "object" ? state : {};
    } catch (_) {
      return {};
    }
  }

  function safeSetValue(id, value) {
    const el = $(id);
    if (!el || value === undefined || value === null) {
      return;
    }
    el.value = String(value);
  }

  function collectUiState(extra = {}) {
    const replyBody = $("agentReplyBody");
    const state = {
      version: 1,
      agent: $("agent") ? $("agent").value : "general",
      model: $("model") ? $("model").value : "auto",
      messageDraft: $("message") ? $("message").value : "",
      jobId: $("jobId") ? $("jobId").value : "",
      semiJobId: $("semiJobId") ? $("semiJobId").value : "",
      outputLog: output ? output.textContent : "",
      agentReply: {
        meta: $("agentReplyMeta") ? $("agentReplyMeta").textContent : DEFAULT_REPLY_META,
        body: replyBody ? replyBody.textContent : DEFAULT_REPLY_BODY,
        isError: replyBody ? replyBody.classList.contains("error") : false,
      },
      updatedAt: new Date().toISOString(),
    };
    return { ...state, ...extra };
  }

  function persistUiState(extra = {}) {
    if (restoringUiState) {
      return;
    }
    try {
      vscode.setState(collectUiState(extra));
    } catch (_) {}
  }

  function restoreUiState() {
    const state = readPersistedUiState();
    if (!state || state.version !== 1) {
      return false;
    }

    restoringUiState = true;
    try {
      safeSetValue("agent", state.agent);
      safeSetValue("model", state.model);
      safeSetValue("message", state.messageDraft);
      safeSetValue("jobId", state.jobId);
      safeSetValue("semiJobId", state.semiJobId);
      if (output && typeof state.outputLog === "string" && state.outputLog.trim()) {
        output.textContent = state.outputLog;
      }
      if (state.agentReply && typeof state.agentReply === "object") {
        setAgentReply(
          state.agentReply.meta || DEFAULT_REPLY_META,
          state.agentReply.body || DEFAULT_REPLY_BODY,
          Boolean(state.agentReply.isError),
          { skipPersist: true },
        );
      }
      return true;
    } finally {
      restoringUiState = false;
    }
  }

  function wireStatePersistence() {
    ["agent", "model", "message", "jobId", "semiJobId"].forEach((id) => {
      const el = $(id);
      if (!el) {
        return;
      }
      el.addEventListener("input", () => persistUiState());
      el.addEventListener("change", () => persistUiState());
    });
    window.addEventListener("beforeunload", () => persistUiState());
    document.addEventListener("visibilitychange", () => persistUiState());
  }

  function headers(extra = {}) {
    const cfg = getConfig();
    const h = { "Content-Type": "application/json", ...extra };
    if (cfg.serverToken) {
      h.Authorization = "Bearer " + cfg.serverToken;
    }
    if (cfg.bridgeToken) {
      h["X-Bridge-Token"] = cfg.bridgeToken;
    }
    return h;
  }

  function requiresServerToken(path) {
    const protectedPrefixes = [
      "/sync",
      "/agent/",
      "/system/chatgpt-bridge/",
      "/trace/",
    ];
    return protectedPrefixes.some((prefix) => String(path || "").startsWith(prefix));
  }

  function buildFetchErrorMessage(url, err) {
    const raw = err && err.message ? String(err.message) : String(err);
    if (/failed to fetch/i.test(raw)) {
      return (
        "無法連線到 " +
        url +
        "；請確認後端服務已啟動、baseUrl 正確，且伺服器已允許 VS Code webview 的 CORS。原始錯誤：" +
        raw
      );
    }
    return raw;
  }

  async function callApi(path, method = "GET", body = null, opts = {}) {
    const cfg = getConfig();
    const timeoutMs = Math.max(
      1000,
      Number((opts && opts.timeoutMs) || DEFAULT_API_TIMEOUT_MS) || DEFAULT_API_TIMEOUT_MS,
    );
    const requireToken = typeof opts.requireToken === "boolean"
      ? opts.requireToken
      : requiresServerToken(path);
    if (!cfg.baseUrl) {
      throw new Error("未設定 serverBaseUrl");
    }
    if (requireToken && !cfg.serverToken) {
      throw new Error("缺少 SERVER_API_TOKEN；這個 API 需要 Bearer token");
    }
    const url = cfg.baseUrl + path;
    const controller = new AbortController();
    const timeoutTimer = setTimeout(() => controller.abort(), timeoutMs);
    const options = { method, headers: headers(), signal: controller.signal };
    const startedAt = Date.now();
    updateBackendActivity({ state: "calling", method, path });
    if (body !== null) {
      options.body = JSON.stringify(body);
    }

    let resp;
    try {
      resp = await fetch(url, options);
    } catch (err) {
      clearTimeout(timeoutTimer);
      if (err && err.name === "AbortError") {
        updateBackendActivity({
          state: "error",
          method,
          path,
          elapsedMs: Date.now() - startedAt,
          error: "請求逾時",
        });
        throw new Error("請求逾時（" + timeoutMs + "ms）： " + url);
      }
      updateBackendActivity({
        state: "error",
        method,
        path,
        elapsedMs: Date.now() - startedAt,
        error: err && err.message ? String(err.message) : String(err),
      });
      throw new Error(buildFetchErrorMessage(url, err));
    }
    clearTimeout(timeoutTimer);
    const text = await resp.text();
    let data = text;
    try {
      data = JSON.parse(text);
    } catch (_) {}
    updateBackendActivity({
      state: resp.ok ? "ok" : "error",
      method,
      path,
      status: resp.status,
      elapsedMs: Date.now() - startedAt,
    });
    return { ok: resp.ok, status: resp.status, data, url };
  }

  function setHealthText(text, ok = false) {
    const el = $("healthStatus");
    el.textContent = text;
    el.style.color = ok ? "#22c55e" : "";
    setPill("healthPill", ok ? "服務：正常" : "服務：異常", ok ? "ok" : "error");
  }

  function setTransportText(text, tone = "normal") {
    const el = $("transportSummary");
    el.textContent = text;
    let pillTone = "warn";
    let pillText = "雲端：待確認";
    if (tone === "ok") {
      el.style.color = "#16a34a";
      pillTone = "ok";
      pillText = "雲端：已連通";
    } else if (tone === "warn") {
      el.style.color = "#d97706";
      pillTone = "warn";
      pillText = "雲端：待確認";
    } else if (tone === "error") {
      el.style.color = "#dc2626";
      pillTone = "error";
      pillText = "雲端：異常";
    } else {
      el.style.color = "";
    }
    setPill("transportPill", pillText, pillTone);
  }

  function setTracePanel(text, tone = "normal") {
    const el = $("tracePanel");
    if (!el) {
      return;
    }
    el.innerHTML = text;
    if (tone === "ok") {
      el.style.color = "#16a34a";
      return;
    }
    if (tone === "warn") {
      el.style.color = "#d97706";
      return;
    }
    if (tone === "error") {
      el.style.color = "#dc2626";
      return;
    }
    el.style.color = "";
  }

  function setControlStatus(text, tone = "normal") {
    const el = $("controlStatus");
    if (!el) {
      return;
    }
    el.textContent = text;
    if (tone === "ok") {
      el.style.color = "#16a34a";
      return;
    }
    if (tone === "warn") {
      el.style.color = "#d97706";
      return;
    }
    if (tone === "error") {
      el.style.color = "#dc2626";
      return;
    }
    el.style.color = "";
  }

  function setMetricsPanel(text, tone = "normal") {
    const el = $("metricsPanel");
    if (!el) {
      return;
    }
    el.innerHTML = text;
    if (tone === "ok") {
      el.style.color = "#16a34a";
      return;
    }
    if (tone === "warn") {
      el.style.color = "#d97706";
      return;
    }
    if (tone === "error") {
      el.style.color = "#dc2626";
      return;
    }
    el.style.color = "";
  }

  function setPill(id, text, tone = "normal") {
    const el = $(id);
    if (!el) {
      return;
    }
    el.textContent = text;
    el.classList.remove("ok", "warn", "error");
    if (tone === "ok" || tone === "warn" || tone === "error") {
      el.classList.add(tone);
    }
  }

  function setAgentReply(metaText, bodyText, isError = false, options = {}) {
    const metaEl = $("agentReplyMeta");
    const bodyEl = $("agentReplyBody");
    if (!metaEl || !bodyEl) {
      return;
    }
    metaEl.textContent = String(metaText || "");
    bodyEl.textContent = String(bodyText || "");
    bodyEl.classList.toggle("error", Boolean(isError));
    if (!options.skipPersist) {
      persistUiState();
    }
  }

  function setSemanticTrendPanel(text, tone = "normal") {
    const el = $("semanticTrendPanel");
    if (!el) {
      return;
    }
    el.innerHTML = String(text || "");
    if (tone === "ok") {
      el.style.color = "#16a34a";
      return;
    }
    if (tone === "warn") {
      el.style.color = "#d97706";
      return;
    }
    if (tone === "error") {
      el.style.color = "#dc2626";
      return;
    }
    el.style.color = "";
  }

  function setLanguageMonitorPanel(text, tone = "normal") {
    const el = $("languageMonitorPanel");
    if (!el) {
      return;
    }
    el.innerHTML = String(text || "");
    if (tone === "ok") {
      el.style.color = "#16a34a";
      return;
    }
    if (tone === "warn") {
      el.style.color = "#d97706";
      return;
    }
    if (tone === "error") {
      el.style.color = "#dc2626";
      return;
    }
    el.style.color = "";
  }

  function formatTs(value) {
    const raw = String(value || "").trim();
    if (!raw) {
      return "";
    }
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) {
      return raw;
    }
    return parsed.toLocaleString("zh-TW", { hour12: false });
  }

  function nowText() {
    return new Date().toLocaleString("zh-TW", { hour12: false });
  }

  function setBackendValue(id, text, tone = "normal") {
    const el = $(id);
    if (!el) {
      return;
    }
    el.textContent = String(text || "");
    el.classList.remove("ok", "warn", "error");
    if (tone === "ok" || tone === "warn" || tone === "error") {
      el.classList.add(tone);
    }
  }

  function updateBackendActivity(activity = {}) {
    const method = String(activity.method || "-").toUpperCase();
    const path = String(activity.path || "-");
    const status = activity.status === undefined || activity.status === null
      ? "-"
      : String(activity.status);
    const elapsedMs = activity.elapsedMs === undefined || activity.elapsedMs === null
      ? "-"
      : String(activity.elapsedMs);
    const state = String(activity.state || "idle");
    let tone = "warn";
    let stateText = "等待後端請求。";

    if (state === "calling") {
      tone = "warn";
      stateText = "正在呼叫後端...";
    } else if (state === "ok") {
      tone = "ok";
      stateText = "後端回應正常。";
    } else if (state === "error") {
      tone = "error";
      stateText = "後端請求失敗。";
    }

    if (activity.error) {
      stateText += " " + String(activity.error);
    }

    setBackendValue("backendState", stateText, tone);
    setBackendValue("backendEndpoint", method + " " + path, tone);
    setBackendValue("backendResponse", "HTTP " + status + " | " + elapsedMs + " ms", tone);
    setBackendValue("backendUpdated", nowText(), "normal");
  }

  function toSafeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function metricTone(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "ok") {
      return "ok";
    }
    if (normalized === "warning") {
      return "warning";
    }
    return "no_data";
  }

  function formatMetricValue(metric) {
    if (!metric || metric.value === null || metric.value === undefined) {
      return "-";
    }
    const value = Number(metric.value);
    if (Number.isNaN(value)) {
      return String(metric.value);
    }
    const unit = String(metric.unit || "").toLowerCase();
    if (unit === "pct") {
      return value.toFixed(2) + "%";
    }
    return value.toFixed(4);
  }

  function summarizeLanguageMonitoring(data) {
    const payload = data && typeof data === "object" ? data : {};
    const metrics = payload.monitoring_metrics && typeof payload.monitoring_metrics === "object"
      ? payload.monitoring_metrics
      : {};
    const selected = [
      metrics.intent_distribution,
      metrics.understanding_score_band,
      metrics.keyword_response_rate,
      metrics.drift_risk,
      metrics.data_gap,
    ].filter((item) => item && typeof item === "object");
    const totalEvents = Number(payload.total_events || 0);
    const sampleStatus = String(payload.sample_status || "insufficient");
    let hasWarning = false;
    let hasNoData = false;

    const chips = selected.map((metric) => {
      const tone = metricTone(metric.status);
      if (tone === "warning") {
        hasWarning = true;
      } else if (tone === "no_data") {
        hasNoData = true;
      }
      return {
        label: String(metric.label || metric.key || "metric"),
        value: formatMetricValue(metric),
        tone,
      };
    });

    let tone = "ok";
    if (hasWarning) {
      tone = "warn";
    } else if (sampleStatus !== "ready" || hasNoData || totalEvents <= 0) {
      tone = "warn";
    }
    const sampleText = sampleStatus === "ready" ? "樣本可用" : "樣本不足";

    return {
      tone,
      sampleText,
      totalEvents,
      windowDays: Number(payload.window_days || 7),
      chips,
    };
  }

  function renderLanguageMonitoringPanel(summary) {
    if (!summary) {
      setLanguageMonitorPanel("語言監控資料不可用。", "error");
      return;
    }
    const chipsHtml = toSafeArray(summary.chips).map((item) => (
      '<div class="language-chip ' + escapeHtml(item.tone) + '">' +
        '<span class="label">' + escapeHtml(item.label) + "</span>" +
        '<span class="value">' + escapeHtml(item.value) + "</span>" +
      "</div>"
    )).join("");

    const html =
      "網狀語言比對監控<br/>" +
      "視窗: " + escapeHtml(String(summary.windowDays)) + " 天" +
      "｜事件: " + escapeHtml(String(summary.totalEvents)) +
      "｜狀態: " + escapeHtml(summary.sampleText) +
      '<div class="language-monitor-grid">' + (chipsHtml || '<div class="hint">無指標</div>') + "</div>";
    setLanguageMonitorPanel(html, summary.tone);
  }

  function statusRank(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "running") {
      return 0;
    }
    if (normalized === "pending") {
      return 1;
    }
    if (normalized === "failed") {
      return 2;
    }
    if (normalized === "completed") {
      return 3;
    }
    if (normalized === "resolved") {
      return 4;
    }
    return 5;
  }

  function resolveRealityState(task) {
    const status = String((task && task.status) || "").toLowerCase();
    if (status === "running") {
      return "running";
    }
    if (status === "pending") {
      return "pending";
    }
    if (status === "failed") {
      return "failed";
    }
    return "idle";
  }

  function normalizeRealityAgentKey(agentKey) {
    const normalized = String(agentKey || "").trim().toLowerCase();
    if (normalized === "learner") {
      return "researcher";
    }
    return normalized || "general";
  }

  function buildTaskIndex(items) {
    const index = {};
    toSafeArray(items).forEach((task) => {
      const key = normalizeRealityAgentKey(task && task.assigned_agent);
      if (!index[key]) {
        index[key] = [];
      }
      index[key].push(task);
    });
    Object.keys(index).forEach((key) => {
      index[key].sort((a, b) => {
        const rankDiff = statusRank(a && a.status) - statusRank(b && b.status);
        if (rankDiff !== 0) {
          return rankDiff;
        }
        const at = new Date((a && a.updated_at) || 0).getTime();
        const bt = new Date((b && b.updated_at) || 0).getTime();
        return bt - at;
      });
    });
    return index;
  }

  function avatarTheme(agentKey) {
    const normalized = String(agentKey || "general").trim().toLowerCase();
    const glyphMap = {
      dispatcher: "控",
      engineer: "工",
      researcher: "研",
      xiaobian: "編",
      whitehat: "盾",
      proclaimer: "言",
      general: "通",
    };
    return {
      theme: "theme-" + (glyphMap[normalized] ? normalized : "general"),
      glyph: glyphMap[normalized] || glyphMap.general,
    };
  }

  function renderAgentAvatar(agentKey, stateClass = "idle") {
    const meta = avatarTheme(agentKey);
    return (
      '<div class="agent-avatar ' + escapeHtml(meta.theme) + " " + escapeHtml(stateClass) + '" aria-hidden="true">' +
        '<span class="agent-avatar-glyph">' + escapeHtml(meta.glyph) + "</span>" +
      "</div>"
    );
  }

  function summarizeTask(task) {
    if (!task) {
      return "目前待命，尚未分配新任務。";
    }
    const title = String(task.title || "").trim();
    const shortDesc = String(task.description || "").trim();
    const display = title || shortDesc || "（無任務標題）";
    const normalizedStatus = String(task.status || "").toLowerCase();
    const statusText = REALITY_STATE_LABEL[resolveRealityState(task)] || normalizedStatus || "待命";
    const updatedText = formatTs(task.updated_at);
    return statusText + "｜" + display + (updatedText ? "\n更新：" + updatedText : "");
  }

  function renderRealityBoard(agentRows) {
    const board = $("realityBoard");
    if (!board) {
      return;
    }
    const rows = toSafeArray(agentRows);
    if (!rows.length) {
      board.innerHTML = '<div class="hint">目前沒有可顯示的智能體資料。</div>';
      return;
    }
    board.innerHTML = rows.map((row) => {
      const stateClass = String(row.state || "idle");
      const stateText = REALITY_STATE_LABEL[stateClass] || "待命";
      return (
        '<div class="reality-card ' + escapeHtml(stateClass) + '">' +
          renderAgentAvatar(row.agentKey, stateClass) +
          '<div class="reality-body">' +
            '<div class="reality-head">' +
              '<div class="reality-name-wrap">' +
                '<span class="state-dot ' + escapeHtml(stateClass) + '"></span>' +
                '<div class="reality-name">' + escapeHtml(row.name) + "</div>" +
              "</div>" +
              '<div class="reality-state ' + escapeHtml(stateClass) + '">' + escapeHtml(stateText) + "</div>" +
            "</div>" +
            '<div class="reality-task">' + escapeHtml(row.taskSummary) + "</div>" +
            '<div class="reality-meta">' +
              '<span class="reality-kpi">任務 <strong>' + escapeHtml(String(row.taskCount || 0)) + "</strong></span>" +
              '<span class="reality-kpi">執行 <strong>' + escapeHtml(String(row.runningCount || 0)) + "</strong></span>" +
              '<span class="reality-kpi">待處理 <strong>' + escapeHtml(String(row.pendingCount || 0)) + "</strong></span>" +
              '<span class="reality-kpi">阻塞 <strong>' + escapeHtml(String(row.failedCount || 0)) + "</strong></span>" +
              '<span class="reality-kpi">更新 <strong>' + escapeHtml(String(row.updatedAt || "-")) + "</strong></span>" +
            "</div>" +
          "</div>" +
        "</div>"
      );
    }).join("");
    renderAgentNetwork(rows);
  }

  function renderAgentNetwork(agentRows) {
    const svg = $("agentNetwork");
    if (!svg) return;
    const rows = toSafeArray(agentRows);
    const stateMap = {};
    rows.forEach(function(row) { stateMap[row.agentKey || ""] = row.state || "idle"; });

    const STATE_COLOR = { running: "#22c55e", pending: "#f59e0b", failed: "#ef4444", idle: "#475569" };
    const STATE_GLOW  = { running: "#22c55e", pending: "#f59e0b", failed: "#ef4444", idle: "#64748b" };

    // Layout: dispatcher center, others in 2 rings for organic feel
    const cx = 150, cy = 148;
    const nodes = [
      { key: "dispatcher",  label: "總管",    x: cx,       y: cy,       r: 28 },
      { key: "engineer",    label: "工程師",  x: cx,       y: cy - 95,  r: 19 },
      { key: "researcher",  label: "研究",    x: cx + 88,  y: cy - 48,  r: 19 },
      { key: "xiaobian",    label: "小編",    x: cx + 80,  y: cy + 62,  r: 17 },
      { key: "general",     label: "通用",    x: cx,       y: cy + 98,  r: 17 },
      { key: "proclaimer",  label: "申言者",  x: cx - 85,  y: cy + 55,  r: 17 },
      { key: "whitehat",    label: "白帽",    x: cx - 88,  y: cy - 52,  r: 19 },
    ];
    // Edges: dispatcher hub + cross-links for InfraNodus feel
    const edges = [
      [0,1],[0,2],[0,3],[0,4],[0,5],[0,6],
      [1,2],[2,3],[3,4],[4,5],[5,6],[6,1],
    ];

    let s = `<defs>`;
    nodes.forEach(function(n) {
      const col = STATE_GLOW[stateMap[n.key]] || STATE_GLOW.idle;
      s += `<filter id="glow-${n.key}" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="4" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>`;
    });
    s += `</defs>`;

    // Draw curved edges
    edges.forEach(function(e) {
      const a = nodes[e[0]], b = nodes[e[1]];
      const midX = (a.x + b.x) / 2 + (Math.random() > 0.5 ? 18 : -18);
      const midY = (a.y + b.y) / 2 + (Math.random() > 0.5 ? 12 : -12);
      const isHub = e[0] === 0 || e[1] === 0;
      s += `<path d="M${a.x},${a.y} Q${midX},${midY} ${b.x},${b.y}"
        fill="none" stroke="rgba(148,163,184,${isHub ? 0.38 : 0.18})"
        stroke-width="${isHub ? 1.5 : 1}" />`;
    });

    // Draw nodes
    nodes.forEach(function(n) {
      const state = stateMap[n.key] || "idle";
      const color = STATE_COLOR[state] || STATE_COLOR.idle;
      const animCls = state === "running" ? " class=\"net-node-running\"" : state === "pending" ? " class=\"net-node-pending\"" : "";
      s += `<circle cx="${n.x}" cy="${n.y}" r="${n.r}"
        fill="${color}" fill-opacity="0.18"
        stroke="${color}" stroke-width="2"
        filter="url(#glow-${n.key})"${animCls} />`;
      s += `<circle cx="${n.x}" cy="${n.y}" r="5" fill="${color}" />`;
      s += `<text x="${n.x}" y="${n.y + n.r + 12}" text-anchor="middle"
        fill="rgba(230,237,246,0.85)" font-size="10"
        font-family="'Noto Sans TC','PingFang TC',sans-serif">${n.label}</text>`;
    });

    svg.innerHTML = s;
  }

  function trendIcon(direction) {
    const normalized = String(direction || "").toLowerCase();
    if (normalized === "up") {
      return "UP";
    }
    if (normalized === "down") {
      return "DOWN";
    }
    return "FLAT";
  }

  function summarizeSemanticTrend(data) {
    const payload = data && typeof data === "object" ? data : {};
    const total = Number(payload.total_events || 0);
    const avg = Number(payload.overall_avg_understanding_score || 0);
    const direction = trendIcon(payload.trend_direction || "flat");
    const latest = formatTs(payload.latest_timestamp || "");
    const dayRows = toSafeArray(payload.daily);
    const compactDaily = dayRows
      .slice(-5)
      .map((row) => {
        const date = String(row.date || "").slice(5);
        const score = Number(row.avg_understanding_score || 0).toFixed(1);
        const count = Number(row.count || 0);
        return date + ":" + score + "(" + count + ")";
      })
      .join(" | ");

    const intents = payload.intent_counts && typeof payload.intent_counts === "object"
      ? payload.intent_counts
      : {};
    const actionCount = Number(intents.action || 0);
    const questionCount = Number(intents.question || 0);
    const discussionCount = Number(intents.discussion || 0);
    const tone = total > 0 ? "ok" : "warn";
    const html =
      "語言比對趨勢（" + SEMANTIC_TREND_DAYS + "日）<br/>" +
      "事件: " + total +
      "｜平均理解分: " + avg.toFixed(1) +
      "｜趨勢: " + direction + "<br/>" +
      "意圖分布 A/Q/D: " + actionCount + "/" + questionCount + "/" + discussionCount + "<br/>" +
      "近5日: " + escapeHtml(compactDaily || "無資料") +
      (latest ? "<br/>最後更新: " + escapeHtml(latest) : "");
    return { html, tone };
  }

  function pickTraceFromPayload(data) {
    const payload = data && typeof data === "object" ? data : {};

    if (payload.latest && typeof payload.latest === "object" && payload.latest.trace_id) {
      return payload.latest;
    }
    if (Array.isArray(payload.items) && payload.items.length > 0) {
      return payload.items[0];
    }
    if (payload.trace_id) {
      return {
        trace_id: payload.trace_id,
        latency: payload.latency,
        ack: payload.ack,
      };
    }

    const fwKey = Object.keys(payload).find((k) => String(k || "").startsWith("fw_"));
    if (fwKey) {
      const row = payload[fwKey] && typeof payload[fwKey] === "object" ? payload[fwKey] : {};
      return { trace_id: fwKey, ...row };
    }
    return { trace_id: "unknown" };
  }

  async function loadLatestTrace() {
    try {
      const result = await callApi("/trace/latest?limit=1", "GET", null, {
        timeoutMs: 45000,
        requireToken: true,
      });
      if (!result.ok) {
        setTracePanel("🔴 Trace 讀取失敗（" + result.status + "）", "error");
        return;
      }

      const trace = pickTraceFromPayload(result.data);
      const traceId = String(trace.trace_id || "unknown");
      const latency = trace.latency ?? ((trace.ack || {}).elapsed_ms ?? "-");
      const status = (trace.ack || {}).status ?? result.data?.status ?? "-";
      const ok = Number(status) === 200;
      const statusIcon = ok ? "🟢" : "🔴";
      setTracePanel(
        statusIcon + " Trace: " + traceId + "<br/>" +
        "⏱ Latency: " + latency + " ms<br/>" +
        "📡 Status: " + status,
        ok ? "ok" : "warn",
      );
    } catch (err) {
      setTracePanel("🔴 Trace 讀取錯誤：" + (err.message || err), "error");
    }
  }

  async function refreshBridgeControlStatus() {
    try {
      const result = await callApi("/system/chatgpt-bridge/control", "GET", null, {
        timeoutMs: 45000,
        requireToken: true,
      });
      if (!result.ok) {
        setControlStatus("控制狀態讀取失敗（" + result.status + "）", "error");
        return;
      }
      const runtime = (result.data && result.data.runtime_control) || {};
      const paused = Boolean(runtime.paused);
      const enabled = Boolean(runtime.effective_enabled);
      const minInterval = runtime.min_interval_seconds ?? "-";
      const maxItems = runtime.max_items ?? "-";
      const cooldown = runtime.cooldown_remaining_seconds ?? "-";
      const modeText = paused ? "已暫停" : (enabled ? "啟用" : "停用");
      const tone = paused ? "warn" : (enabled ? "ok" : "warn");
      setControlStatus(
        "狀態：" + modeText +
          "｜間隔：" + minInterval + "s" +
          "｜樣本：" + maxItems +
          "｜冷卻：" + cooldown + "s",
        tone,
      );
      if (String(minInterval) !== "-" && $("controlInterval")) {
        $("controlInterval").value = String(minInterval);
      }
      if (String(maxItems) !== "-" && $("controlMaxItems")) {
        $("controlMaxItems").value = String(maxItems);
      }
    } catch (err) {
      setControlStatus("控制狀態讀取錯誤：" + (err.message || err), "error");
    }
  }

  async function sendBridgeControl(action, extra = {}) {
    const payload = { action, actor: "cursor_sidebar", ...extra };
    const result = await callApi("/system/chatgpt-bridge/control", "POST", payload, {
      timeoutMs: 45000,
      requireToken: true,
    });
    if (!result.ok) {
      throw new Error("控制 API 失敗（" + result.status + "）");
    }
    await refreshBridgeControlStatus();
    return result;
  }

  async function applyBridgeControl() {
    const intervalRaw = ($("controlInterval").value || "").trim();
    const maxItemsRaw = ($("controlMaxItems").value || "").trim();
    const payload = {};
    if (intervalRaw) {
      payload.min_interval_seconds = Number(intervalRaw);
    }
    if (maxItemsRaw) {
      payload.max_items = Number(maxItemsRaw);
    }
    if (!Object.keys(payload).length) {
      logLine("請先填入最小間隔或樣本數。");
      return;
    }
    const result = await sendBridgeControl("set", payload);
    logLine("橋接控制已更新：" + JSON.stringify(result.data, null, 2));
  }

  async function loadLearningMetrics() {
    try {
      const result = await callApi("/trace/learning-status?window_minutes=180&limit=500", "GET", null, {
        timeoutMs: 45000,
        requireToken: true,
      });
      if (!result.ok) {
        setMetricsPanel("🔴 指標讀取失敗（" + result.status + "）", "error");
        return;
      }
      const data = result.data || {};
      const current = (data.current && typeof data.current === "object") ? data.current : {};
      const readiness = (data.readiness && typeof data.readiness === "object") ? data.readiness : {};
      const reason = String(readiness.reason || (data.learning_ready ? "已達可學習門檻" : "樣本不足"));
      const ready = Boolean(data.learning_ready);
      const tone = ready ? "ok" : "warn";
      setMetricsPanel(
        (ready ? "🟢" : "🟡") + " Learning: " + String(data.learning_stage || "-") + "<br/>" +
        "✅ 成功率: " + String(current.success_rate_pct ?? "-") + "%<br/>" +
        "❌ 錯誤率: " + String(current.error_rate_pct ?? "-") + "%<br/>" +
        "📦 樣本數: " + String(current.total ?? "-") + "（歷史 " + String(data.history_total ?? "-") + "）<br/>" +
        "⏱ 平均延遲: " + String(current.latency_avg_ms ?? "-") + " ms<br/>" +
        "🧩 門檻說明: " + reason,
        tone,
      );
    } catch (err) {
      setMetricsPanel("🔴 指標讀取錯誤：" + (err.message || err), "error");
    }
  }

  function parseTraceLine(line, kind) {
    const text = String(line || "");
    const traceMatch = text.match(/trace=([a-zA-Z0-9_-]+)/);
    if (!traceMatch) {
      return null;
    }
    const entry = {
      kind,
      trace: traceMatch[1],
      line: text,
    };

    if (kind === "ack") {
      const httpMatch = text.match(/http=([0-9]+)/);
      const elapsedMatch = text.match(/elapsed_ms=([0-9]+)/);
      const requestIdMatch = text.match(/cloud_request_id=([^ ]+)/);
      entry.http = httpMatch ? Number(httpMatch[1]) : null;
      entry.elapsedMs = elapsedMatch ? Number(elapsedMatch[1]) : null;
      entry.cloudRequestId = requestIdMatch ? requestIdMatch[1] : "";
    }
    return entry;
  }

  function analyzeTransport(logLines) {
    const lines = Array.isArray(logLines) ? logLines : [];
    const forwardings = [];
    const acks = [];
    const errors = [];

    lines.forEach((line, idx) => {
      const text = String(line || "");
      if (text.includes("forwarding trace=")) {
        const parsed = parseTraceLine(text, "forwarding");
        if (parsed) {
          parsed.index = idx;
          forwardings.push(parsed);
        }
        return;
      }
      if (text.includes("cloud_ack trace=")) {
        const parsed = parseTraceLine(text, "ack");
        if (parsed) {
          parsed.index = idx;
          acks.push(parsed);
        }
        return;
      }
      if (text.includes("API error trace=") || text.includes("request failed trace=")) {
        const parsed = parseTraceLine(text, "error");
        if (parsed) {
          parsed.index = idx;
          errors.push(parsed);
        }
      }
    });

    const latestForward = forwardings.length ? forwardings[forwardings.length - 1] : null;
    const latestAck = acks.length ? acks[acks.length - 1] : null;
    const latestError = errors.length ? errors[errors.length - 1] : null;
    let matchedAck = null;

    if (latestForward) {
      for (let i = acks.length - 1; i >= 0; i -= 1) {
        if (acks[i].trace === latestForward.trace) {
          matchedAck = acks[i];
          break;
        }
      }
    }

    if (matchedAck && (!latestError || latestError.index < matchedAck.index)) {
      return {
        tone: "ok",
        summary:
          "雲端已對接（trace=" +
          matchedAck.trace +
          ", http=" +
          (matchedAck.http ?? "n/a") +
          ", " +
          (matchedAck.elapsedMs ?? "n/a") +
          "ms）",
        details: [latestForward?.line || "", matchedAck.line].filter(Boolean),
      };
    }

    if (latestError) {
      return {
        tone: "error",
        summary: "最近一次雲端對接失敗（trace=" + latestError.trace + "）",
        details: [latestForward?.line || "", latestError.line].filter(Boolean),
      };
    }

    if (latestForward && !matchedAck) {
      return {
        tone: "warn",
        summary: "已送出到雲端但尚未看到回執（trace=" + latestForward.trace + "）",
        details: [latestForward.line],
      };
    }

    if (latestAck) {
      return {
        tone: "ok",
        summary: "最近有雲端回執（trace=" + latestAck.trace + "）",
        details: [latestAck.line],
      };
    }

    return {
      tone: "warn",
      summary: "尚未找到 forwarding/cloud_ack 記錄，請先觸發一次 bridge。",
      details: [],
    };
  }

  function toneFromTransportState(state) {
    const normalized = String(state || "").toLowerCase();
    if (normalized === "ok" || normalized === "ack_only") {
      return "ok";
    }
    if (
      normalized === "pending" ||
      normalized === "no_events" ||
      normalized === "missing_log"
    ) {
      return "warn";
    }
    return "error";
  }

  async function loadRealityBoard() {
    if (realityLoadInFlight) {
      return;
    }
    realityLoadInFlight = true;
    try {
      const fetchWithTokenFallback = async (path) => {
        const first = await callApi(path, "GET", null, {
          timeoutMs: REALITY_API_TIMEOUT_MS,
          requireToken: false,
        });
        if (first.ok || (first.status !== 401 && first.status !== 403)) {
          return first;
        }
        return callApi(path, "GET", null, {
          timeoutMs: REALITY_API_TIMEOUT_MS,
          requireToken: true,
        });
      };

      const [agentsResult, tasksResult, trendResult, languageResult] = await Promise.all([
        fetchWithTokenFallback("/agents"),
        fetchWithTokenFallback(
          "/agent/tasks?status=unresolved&limit=200&failed_scope=recent&failed_window_hours="
            + encodeURIComponent(String(REALITY_FAILED_WINDOW_HOURS)),
        ),
        fetchWithTokenFallback("/agent/semantic-trend?days=" + encodeURIComponent(String(SEMANTIC_TREND_DAYS))),
        fetchWithTokenFallback("/system/language-monitoring?days=7&limit=2500"),
      ]);

      const agentsPayload = toSafeArray(agentsResult.data);
      const tasksPayload = tasksResult.data && typeof tasksResult.data === "object"
        ? toSafeArray(tasksResult.data.items)
        : [];
      const taskIndex = buildTaskIndex(tasksPayload);

      const keyedAgents = {};
      agentsPayload.forEach((agent) => {
        const key = String((agent && agent.key) || "").trim().toLowerCase();
        if (key) {
          keyedAgents[key] = agent;
        }
      });

      const mergedKeys = [];
      REALITY_AGENTS_ORDER.forEach((key) => {
        if (mergedKeys.indexOf(key) === -1) {
          mergedKeys.push(key);
        }
      });
      Object.keys(keyedAgents).forEach((key) => {
        if (mergedKeys.indexOf(key) === -1) {
          mergedKeys.push(key);
        }
      });

      const rows = mergedKeys.map((key) => {
        const agent = keyedAgents[key] || {};
        const tasksForAgent = toSafeArray(taskIndex[key]);
        const task = tasksForAgent[0] || null;
        const runningCount = tasksForAgent.filter((item) => resolveRealityState(item) === "running").length;
        const pendingCount = tasksForAgent.filter((item) => resolveRealityState(item) === "pending").length;
        const failedCount = tasksForAgent.filter((item) => resolveRealityState(item) === "failed").length;
        let state = "idle";
        if (runningCount > 0) {
          state = "running";
        } else if (pendingCount > 0) {
          state = "pending";
        } else if (failedCount > 0) {
          state = "failed";
        }
        const latestUpdatedTask = tasksForAgent.find((item) => item && item.updated_at) || task;
        const fallbackName = REALITY_AGENT_LABEL[key] || key || "智能體";
        const name = String(agent.label || fallbackName);
        return {
          agentKey: key || "general",
          name,
          state,
          taskSummary: summarizeTask(task),
          taskCount: tasksForAgent.length,
          runningCount,
          pendingCount,
          failedCount,
          updatedAt: latestUpdatedTask ? formatTs(latestUpdatedTask.updated_at) : "",
        };
      });
      renderRealityBoard(rows);

      if (trendResult.ok) {
        const trend = summarizeSemanticTrend(trendResult.data || {});
        setSemanticTrendPanel(trend.html, trend.tone);
      } else {
        setSemanticTrendPanel(
          "語言比對趨勢讀取失敗（HTTP " + trendResult.status + "）",
          "error",
        );
      }

      if (languageResult.ok) {
        const languageSummary = summarizeLanguageMonitoring(languageResult.data || {});
        renderLanguageMonitoringPanel(languageSummary);
      } else {
        setLanguageMonitorPanel(
          "語言監控讀取失敗（HTTP " + String(languageResult.status) + "）",
          "error",
        );
      }
      realityLastError = "";
    } catch (err) {
      const message = err && err.message ? String(err.message) : String(err);
      renderRealityBoard([]);
      setSemanticTrendPanel("語言比對趨勢讀取錯誤：" + escapeHtml(message), "error");
      setLanguageMonitorPanel("語言監控讀取錯誤：" + escapeHtml(message), "error");
      if (message !== realityLastError) {
        logLine("實境面板更新失敗：" + message);
        realityLastError = message;
      }
    } finally {
      realityLoadInFlight = false;
    }
  }

  async function checkHealth() {
    try {
      const result = await callApi("/health", "GET", null, { timeoutMs: 15000, requireToken: false });
      if (result.ok) {
        setHealthText("健康檢查正常（" + result.status + "）", true);
        logLine("GET /health -> " + result.status);
      } else {
        setHealthText("健康檢查失敗（" + result.status + "）");
        logLine("GET /health -> " + result.status + " " + JSON.stringify(result.data));
      }
    } catch (err) {
      setHealthText("健康檢查錯誤：" + (err.message || err));
      logLine("健康檢查錯誤：" + (err.message || err));
    }
  }

  async function checkTransport() {
    const path = "/system/chatgpt-bridge/latest-sync?history_limit=3&include_log_tail=true&tail_lines=80&transport_scan_lines=2000";
    try {
      const result = await callApi(path, "GET", null, {
        timeoutMs: 90000,
        requireToken: true,
      });
      if (!result.ok) {
        setTransportText("雲端對接檢查失敗（" + result.status + "）", "error");
        $("transportDetails").textContent = JSON.stringify(result.data, null, 2);
        logLine("GET " + path + " -> " + result.status);
        return;
      }

      const data = result.data || {};
      const bridge = data.bridge || {};
      const trace = (data.trace && typeof data.trace === "object") ? data.trace : {};
      const latestTrace = (trace.latest && typeof trace.latest === "object") ? trace.latest : null;
      const serverTransport = (data.transport && typeof data.transport === "object")
        ? data.transport
        : null;
      const logTail = ((data.monitor_log || {}).tail || []).map((v) => String(v || ""));

      let analysis = null;
      if (latestTrace && (latestTrace.forward || latestTrace.ack || latestTrace.error)) {
        const traceId = String(latestTrace.trace_id || "-");
        const latency = latestTrace.latency ?? ((latestTrace.ack || {}).elapsed_ms ?? "-");
        const statusCode = (latestTrace.ack || {}).status ?? "-";
        const statusText = String(latestTrace.status || "");
        const traceTone = statusText === "error"
          ? "error"
          : ((latestTrace.ack && statusCode === 200) ? "ok" : "warn");
        const details = [];
        if (latestTrace.forward && latestTrace.forward.time_iso) {
          details.push("forward: " + latestTrace.forward.time_iso);
        }
        if (latestTrace.ack) {
          details.push(
            "ack: status=" + statusCode +
            ", latency=" + latency + "ms" +
            ", request_id=" + String(latestTrace.ack.cloud_request_id || "n/a"),
          );
        }
        if (latestTrace.error && latestTrace.error.error) {
          details.push("error: " + String(latestTrace.error.error));
        }
        analysis = {
          tone: traceTone,
          summary: "Trace " + traceId + "｜Latency " + latency + "ms｜Status " + statusCode,
          details,
        };
      } else if (serverTransport && serverTransport.summary) {
        const details = [];
        const latestForwarding = serverTransport.latest_forwarding || null;
        const matchedAck = serverTransport.matched_ack_for_latest_forwarding || null;
        const latestAck = serverTransport.latest_ack || null;
        const latestError = serverTransport.latest_error || null;

        if (latestForwarding && latestForwarding.line) {
          details.push(latestForwarding.line);
        }
        if (matchedAck && matchedAck.line) {
          details.push(matchedAck.line);
        } else if (latestAck && latestAck.line) {
          details.push(latestAck.line);
        }
        if (latestError && latestError.line) {
          details.push(latestError.line);
        }

        analysis = {
          tone: toneFromTransportState(serverTransport.state),
          summary: String(serverTransport.summary),
          details,
        };
      } else {
        analysis = analyzeTransport(logTail);
      }

      const syncStatus = String(bridge.full_sync_last_status || "unknown");
      const syncMessage = String(bridge.full_sync_last_message || "");
      const semiSyncStatus = String(bridge.semi_full_sync_last_status || "unknown");
      const semiSyncMessage = String(bridge.semi_full_sync_last_message || "");
      const summary = analysis.summary + "｜全量同步：" + syncStatus + "｜半全量同步：" + semiSyncStatus;
      setTransportText(summary, analysis.tone);
      $("transportDetails").textContent = [
        syncMessage ? ("同步摘要：" + syncMessage) : "",
        semiSyncMessage ? ("半全量摘要：" + semiSyncMessage) : "",
        ...analysis.details,
      ].filter(Boolean).join("\n");
      logLine("GET " + path + " -> " + result.status + "（" + analysis.summary + "）");
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      setTransportText("雲端對接檢查錯誤：" + message, "error");
      $("transportDetails").textContent = "";
      logLine("雲端對接檢查錯誤：" + message);
    }
  }

  function toggleSecretField(inputId, buttonId) {
    const input = $(inputId);
    const button = $(buttonId);
    if (!input || !button) {
      return;
    }
    const visible = input.type === "text";
    input.type = visible ? "password" : "text";
    button.textContent = visible ? "顯示" : "隱藏";
  }

  async function sendAgentMessage() {
    const message = ($("message").value || "").trim();
    const agent = $("agent").value;
    const model = $("model").value;
    const sendBtn = $("sendAgent");
    if (!message) {
      logLine("訊息為空，請先輸入內容。");
      return;
    }

    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = "送出中...";
    }
    setAgentReply(
      "正在處理：agent=" + agent + " | model=" + model,
      "請稍候，正在等待智能體回覆...",
      false,
    );
    logLine("POST /chat/agent -> agent=" + agent + ", model=" + model);

    try {
      const result = await callApi("/chat/agent", "POST", { message, agent, model }, {
        timeoutMs: CHAT_API_TIMEOUT_MS,
        requireToken: false,
      });
      const payload = (result.data && typeof result.data === "object") ? result.data : {};
      const responseText = String(payload.response || payload.reply || "").trim();
      const responseTime = payload.response_time !== undefined ? payload.response_time : null;
      const resolvedAgent = String(payload.agent || agent || "-");
      const resolvedModel = String(payload.model || model || "-");

      if (!result.ok || payload.error) {
        const reason = String(payload.error || payload.message || "請求失敗").trim();
        const hint = result.status === 403
          ? "（請確認 SERVER_API_TOKEN 是否已設定且正確）"
          : "";
        setAgentReply(
          "回覆失敗：HTTP " + result.status + " | agent=" + resolvedAgent,
          reason + (hint ? "\n" + hint : ""),
          true,
        );
        logLine("回應 " + result.status + "：" + JSON.stringify(result.data, null, 2));
        postTerminalLog("[智能體錯誤] agent=" + resolvedAgent + " | http=" + result.status + " | " + reason);
        return;
      }

      const timeText = (responseTime === null || responseTime === undefined) ? "-" : String(responseTime) + "s";
      const mainText = responseText || "（回覆為空）";
      setAgentReply(
        "回覆成功：agent=" + resolvedAgent + " | model=" + resolvedModel + " | time=" + timeText,
        mainText,
        false,
      );
      logLine("回應 " + result.status + "：" + JSON.stringify(result.data, null, 2));
      postTerminalLog("[智能體回覆] agent=" + resolvedAgent + " | model=" + resolvedModel + "\n" + mainText);
      $("message").value = "";
    } catch (err) {
      const msg = err && err.message ? String(err.message) : String(err);
      setAgentReply(
        "回覆失敗：連線/逾時",
        msg + "\n建議：確認 baseUrl、token 與後端服務狀態。",
        true,
      );
      logLine("智能體請求錯誤：" + msg);
      postTerminalLog("[智能體錯誤] " + msg);
    } finally {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.textContent = "送出";
      }
    }
  }

  async function startFullSync() {
    logLine("POST /sync type=full_sync async=true");
    const result = await callApi("/sync", "POST", {
      type: "full_sync",
      async: true,
      source: "cursor_extension_sidebar",
    }, {
      timeoutMs: SYNC_API_TIMEOUT_MS,
      requireToken: true,
    });
    logLine("回應 " + result.status + "：" + JSON.stringify(result.data, null, 2));
    if (result.ok && result.data && result.data.job_id) {
      $("jobId").value = result.data.job_id;
      persistUiState();
    }
  }

  async function startSemiFullSync() {
    logLine("POST /sync type=semi_full_sync async=true");
    const result = await callApi("/sync", "POST", {
      type: "semi_full_sync",
      async: true,
      source: "cursor_extension_sidebar_semi_full",
    }, {
      timeoutMs: SYNC_API_TIMEOUT_MS,
      requireToken: true,
    });
    logLine("回應 " + result.status + "：" + JSON.stringify(result.data, null, 2));
    if (result.ok && result.data && result.data.job_id) {
      $("semiJobId").value = result.data.job_id;
      persistUiState();
    }
  }

  async function pollJob(options = {}) {
    const silentIfEmpty = Boolean(options.silentIfEmpty);
    const jobId = ($("jobId").value || "").trim();
    if (!jobId) {
      if (!silentIfEmpty) {
        logLine("job_id 為空，請先輸入任務 ID。");
      }
      return null;
    }
    const path = "/sync/full-sync/jobs/" + encodeURIComponent(jobId);
    const result = await callApi(path, "GET", null, {
      timeoutMs: 30000,
      requireToken: true,
    });
    logLine("GET " + path + " -> " + result.status + " " + JSON.stringify(result.data, null, 2));
  }

  async function pollSemiJob(options = {}) {
    const silentIfEmpty = Boolean(options.silentIfEmpty);
    const jobId = ($("semiJobId").value || "").trim();
    if (!jobId) {
      if (!silentIfEmpty) {
        logLine("半全量 job_id 為空，請先輸入任務 ID。");
      }
      return null;
    }
    const path = "/sync/semi-full-sync/jobs/" + encodeURIComponent(jobId);
    const result = await callApi(path, "GET", null, {
      timeoutMs: 30000,
      requireToken: true,
    });
    logLine("GET " + path + " -> " + result.status + " " + JSON.stringify(result.data, null, 2));
  }

  async function listJobs() {
    const result = await callApi("/sync/full-sync/jobs?limit=10", "GET", null, {
      timeoutMs: 30000,
      requireToken: true,
    });
    logLine("GET /sync/full-sync/jobs -> " + result.status + " " + JSON.stringify(result.data, null, 2));
  }

  async function listSemiJobs() {
    const result = await callApi("/sync/semi-full-sync/jobs?limit=10", "GET", null, {
      timeoutMs: 30000,
      requireToken: true,
    });
    logLine("GET /sync/semi-full-sync/jobs -> " + result.status + " " + JSON.stringify(result.data, null, 2));
  }

  function toggleAutoPoll() {
    if (autoPollTimer) {
      clearInterval(autoPollTimer);
      autoPollTimer = null;
      $("toggleAutoPoll").textContent = "自動輪詢：關閉";
      logLine("已停止自動輪詢。");
      return;
    }
    const jobId = ($("jobId").value || "").trim();
    if (!jobId) {
      logLine("請先填入全量同步 job_id，再啟用自動輪詢。");
      return;
    }
    autoPollTimer = setInterval(() => {
      pollJob({ silentIfEmpty: true }).catch((err) => logLine("自動輪詢錯誤：" + (err.message || err)));
    }, 3000);
    $("toggleAutoPoll").textContent = "自動輪詢：啟用";
    logLine("已啟用自動輪詢（每 3 秒）。");
  }

  function toggleSemiAutoPoll() {
    if (semiAutoPollTimer) {
      clearInterval(semiAutoPollTimer);
      semiAutoPollTimer = null;
      $("toggleSemiAutoPoll").textContent = "自動輪詢：關閉";
      logLine("已停止半全量自動輪詢。");
      return;
    }
    const jobId = ($("semiJobId").value || "").trim();
    if (!jobId) {
      logLine("請先填入半全量 job_id，再啟用自動輪詢。");
      return;
    }
    semiAutoPollTimer = setInterval(() => {
      pollSemiJob({ silentIfEmpty: true }).catch((err) => logLine("半全量自動輪詢錯誤：" + (err.message || err)));
    }, 3000);
    $("toggleSemiAutoPoll").textContent = "自動輪詢：啟用";
    logLine("已啟用半全量自動輪詢（每 3 秒）。");
  }

  function toggleTransportPoll() {
    if (transportPollTimer) {
      clearInterval(transportPollTimer);
      transportPollTimer = null;
      $("toggleTransportPoll").textContent = "自動檢查：關閉";
      logLine("已停止雲端對接自動檢查。");
      return;
    }
    transportPollTimer = setInterval(() => {
      checkTransport().catch((err) => logLine("雲端對接自動檢查錯誤：" + (err.message || err)));
    }, TRANSPORT_POLL_MS);
    $("toggleTransportPoll").textContent = "自動檢查：啟用";
    logLine("已啟用雲端對接自動檢查（每 " + Math.round(TRANSPORT_POLL_MS / 1000) + " 秒）。");
  }

  function wireEvents() {
    $("saveConfig").addEventListener("click", () => {
      const payload = {
        serverBaseUrl: $("baseUrl").value,
        serverToken: $("serverToken").value,
        bridgeToken: $("bridgeToken").value,
      };
      vscode.postMessage({ type: "saveConfig", payload });
      logLine("設定已儲存到工作區設定。");
    });

    $("checkHealth").addEventListener("click", () =>
      checkHealth().catch((err) => logLine("健康檢查錯誤：" + (err.message || err))),
    );
    $("toggleServerToken").addEventListener("click", () => toggleSecretField("serverToken", "toggleServerToken"));
    $("toggleBridgeToken").addEventListener("click", () => toggleSecretField("bridgeToken", "toggleBridgeToken"));
    $("sendAgent").addEventListener("click", () =>
      sendAgentMessage().catch((err) => logLine("智能體請求錯誤：" + (err.message || err))),
    );
    $("message").addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        sendAgentMessage().catch((err) => logLine("智能體請求錯誤：" + (err.message || err)));
      }
    });
    $("startSync").addEventListener("click", () =>
      startFullSync().catch((err) => logLine("同步錯誤：" + (err.message || err))),
    );
    $("startSemiSync").addEventListener("click", () =>
      startSemiFullSync().catch((err) => logLine("半全量同步錯誤：" + (err.message || err))),
    );
    $("pollJob").addEventListener("click", () =>
      pollJob().catch((err) => logLine("輪詢錯誤：" + (err.message || err))),
    );
    $("pollSemiJob").addEventListener("click", () =>
      pollSemiJob().catch((err) => logLine("半全量輪詢錯誤：" + (err.message || err))),
    );
    $("listJobs").addEventListener("click", () =>
      listJobs().catch((err) => logLine("任務列表錯誤：" + (err.message || err))),
    );
    $("listSemiJobs").addEventListener("click", () =>
      listSemiJobs().catch((err) => logLine("半全量任務列表錯誤：" + (err.message || err))),
    );
    $("toggleAutoPoll").addEventListener("click", toggleAutoPoll);
    $("toggleSemiAutoPoll").addEventListener("click", toggleSemiAutoPoll);
    $("checkTransport").addEventListener("click", () =>
      checkTransport().catch((err) => logLine("雲端對接檢查錯誤：" + (err.message || err))),
    );
    $("toggleTransportPoll").addEventListener("click", toggleTransportPoll);
    $("pauseBridge").addEventListener("click", () =>
      sendBridgeControl("pause")
        .then((result) => logLine("Bridge 已暫停：" + JSON.stringify(result.data, null, 2)))
        .catch((err) => logLine("Bridge 暫停失敗：" + (err.message || err))),
    );
    $("resumeBridge").addEventListener("click", () =>
      sendBridgeControl("resume")
        .then((result) => logLine("Bridge 已恢復：" + JSON.stringify(result.data, null, 2)))
        .catch((err) => logLine("Bridge 恢復失敗：" + (err.message || err))),
    );
    $("applyBridgeControl").addEventListener("click", () =>
      applyBridgeControl().catch((err) => logLine("Bridge 控制更新失敗：" + (err.message || err))),
    );
    $("resetBridgeCooldown").addEventListener("click", () =>
      sendBridgeControl("reset_cooldown")
        .then((result) => logLine("Bridge 冷卻已重置：" + JSON.stringify(result.data, null, 2)))
        .catch((err) => logLine("Bridge 冷卻重置失敗：" + (err.message || err))),
    );
    $("refreshMetrics").addEventListener("click", () =>
      loadLearningMetrics().catch((err) => logLine("Learning 指標刷新失敗：" + (err.message || err))),
    );
  }

  hydrateInitialConfig();
  setPill("healthPill", "服務：未檢查", "warn");
  setPill("transportPill", "雲端：未檢查", "warn");
  setAgentReply(DEFAULT_REPLY_META, DEFAULT_REPLY_BODY, false, { skipPersist: true });
  setSemanticTrendPanel("語言比對趨勢載入中...", "warn");
  setLanguageMonitorPanel("語言監控指標載入中...", "warn");
  const restoredUiState = restoreUiState();
  wireEvents();
  wireStatePersistence();
  if (restoredUiState) {
    logLine("已恢復上次控制台狀態：智能體、模型、輸入草稿、job_id、上一則回覆與輸出紀錄。");
  }
  loadRealityBoard().catch((err) => logLine("啟動時實境面板載入錯誤：" + (err.message || err)));
  loadLatestTrace().catch((err) => logLine("啟動時 Trace 載入錯誤：" + (err.message || err)));
  refreshBridgeControlStatus().catch((err) => logLine("啟動時控制狀態讀取錯誤：" + (err.message || err)));
  loadLearningMetrics().catch((err) => logLine("啟動時 Learning 指標讀取錯誤：" + (err.message || err)));
  if (latestTraceTimer) {
    clearInterval(latestTraceTimer);
  }
  latestTraceTimer = setInterval(() => {
    loadLatestTrace().catch((err) => logLine("Trace 輪詢錯誤：" + (err.message || err)));
  }, TRACE_POLL_MS);
  if (metricsTimer) {
    clearInterval(metricsTimer);
  }
  metricsTimer = setInterval(() => {
    loadLearningMetrics().catch((err) => logLine("Learning 指標輪詢錯誤：" + (err.message || err)));
    refreshBridgeControlStatus().catch((err) => logLine("控制狀態輪詢錯誤：" + (err.message || err)));
  }, METRICS_POLL_MS);
  if (realityTimer) {
    clearInterval(realityTimer);
  }
  realityTimer = setInterval(() => {
    loadRealityBoard().catch((err) => logLine("實境面板輪詢錯誤：" + (err.message || err)));
  }, REALITY_POLL_MS);
  checkTransport().catch((err) => logLine("啟動時雲端對接檢查錯誤：" + (err.message || err)));
})();

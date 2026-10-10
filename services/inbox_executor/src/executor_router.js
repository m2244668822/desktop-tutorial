import { classifyMechanicalActions, currentTaskEnvelope } from "./inbox.js";

const EXECUTORS = new Set(["auto", "mechanical", "inbox-daemon", "codex", "cursor", "vscode"]);
const ROUTES = new Set(["mechanical", "agentic"]);

export function contractField(text, name) {
  const escaped = String(name).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const envelope = currentTaskEnvelope(text);
  const match = envelope.match(
    new RegExp("^\\s*" + escaped + "\\s+(?:`([^`]+)`|([^\\s#]+))\\s*$", "mi")
  );
  return String(match?.[1] || match?.[2] || "").trim();
}

function normalizeRequested(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return { requested: "auto", valid: true };
  return { requested: raw, valid: EXECUTORS.has(raw) };
}

function readiness(capabilities, executor) {
  const row = capabilities?.executor_readiness?.[executor] || {};
  return {
    installed: Boolean(row.installed),
    authenticated: Boolean(row.authenticated),
    headless_ready: Boolean(row.headless_ready),
    interactive_only: Boolean(row.interactive_only),
  };
}

function parsePercent(value, fallback) {
  if (value === undefined || value === null || String(value).trim() === "") return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(100, parsed));
}

function truthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function executorLoadHint(env, name) {
  const upper = name.toUpperCase();
  return {
    capacity: parsePercent(env[`WHITE_STUDIO_${upper}_CAPACITY`], 100),
    load: parsePercent(env[`WHITE_STUDIO_${upper}_LOAD`], 0),
    busy: truthy(env[`WHITE_STUDIO_${upper}_BUSY`]),
  };
}

function hasCapacityHints(env) {
  return ["CODEX", "CURSOR"].some((name) =>
    ["CAPACITY", "LOAD", "BUSY"].some((field) =>
      Object.prototype.hasOwnProperty.call(env, `WHITE_STUDIO_${name}_${field}`)
    )
  );
}

export function routeInboxTask(text, capabilities = {}, env = process.env) {
  const requestedState = normalizeRequested(contractField(text, "executor"));
  const requested = requestedState.requested;
  const explicitRoute = String(contractField(text, "route") || "").toLowerCase();
  const mechanical = classifyMechanicalActions(text);
  const route = ROUTES.has(explicitRoute)
    ? explicitRoute
    : mechanical.ok
      ? "mechanical"
      : "agentic";

  if (!requestedState.valid) {
    return {
      ok: false,
      route,
      requested_executor: requested,
      selected_executor: null,
      reason: "unknown_executor",
      code: "invalid_executor",
      headless: true,
      requires_ui: false,
    };
  }

  if (route === "mechanical") {
    if (!mechanical.ok) {
      return {
        ok: false,
        route,
        requested_executor: requested,
        selected_executor: null,
        reason: mechanical.code || "missing_actions",
        code: mechanical.code || "missing_actions",
        headless: true,
        requires_ui: false,
      };
    }
    return {
      ok: true,
      route,
      requested_executor: requested,
      selected_executor: "inbox-daemon",
      reason: "mechanical_actions_present",
      code: "ok",
      headless: true,
      requires_ui: false,
    };
  }

  const project = contractField(text, "project");
  if (!project) {
    return {
      ok: false,
      route,
      requested_executor: requested,
      selected_executor: null,
      reason: "agentic_project_required",
      code: "project_required",
      headless: true,
      requires_ui: false,
    };
  }

  if (requested === "mechanical" || requested === "inbox-daemon") {
    return {
      ok: false,
      route,
      requested_executor: requested,
      selected_executor: null,
      reason: "agentic_task_requested_mechanical_executor",
      code: "executor_mismatch",
      headless: true,
      requires_ui: false,
    };
  }

  if (requested === "vscode") {
    const state = readiness(capabilities, "vscode");
    return {
      ok: false,
      route,
      requested_executor: requested,
      selected_executor: state.installed ? "vscode" : null,
      reason: state.installed ? "vscode_requires_interactive_agent_host" : "vscode_unavailable",
      code: state.installed ? "interactive_executor_required" : "executor_unavailable",
      headless: false,
      requires_ui: true,
    };
  }

  const canUse = (name) => readiness(capabilities, name).headless_ready;

  if (requested === "codex" || requested === "cursor") {
    if (!canUse(requested)) {
      return {
        ok: false,
        route,
        requested_executor: requested,
        selected_executor: null,
        reason: requested + "_not_headless_ready",
        code: "executor_unavailable",
        headless: true,
        requires_ui: false,
      };
    }
    return {
      ok: true,
      route,
      requested_executor: requested,
      selected_executor: requested,
      reason: "explicit_executor_ready",
      code: "ok",
      headless: true,
      requires_ui: false,
    };
  }

  const order = String(env.WHITE_STUDIO_EXECUTOR_ORDER || "codex,cursor")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter((item) => item === "codex" || item === "cursor");

  const uniqueOrder = [...new Set(order)];

  if (hasCapacityHints(env)) {
    const ranked = uniqueOrder
      .map((candidate, index) => {
        const hint = executorLoadHint(env, candidate);
        const ready = canUse(candidate);
        const score = ready && !hint.busy && hint.capacity > 0
          ? hint.capacity - hint.load
          : -1;
        return { candidate, index, ready, score, ...hint };
      })
      .filter((item) => item.ready && item.score >= 0)
      .sort((a, b) => (b.score - a.score) || (a.index - b.index));

    if (ranked.length > 0) {
      const picked = ranked[0];
      return {
        ok: true,
        route,
        requested_executor: "auto",
        selected_executor: picked.candidate,
        reason: "capacity_selected_" + picked.candidate,
        code: "ok",
        headless: true,
        requires_ui: false,
        scheduler: {
          policy: "capacity-aware-v1",
          capacity: picked.capacity,
          load: picked.load,
          score: picked.score,
        },
      };
    }
  }

  for (const candidate of uniqueOrder) {
    if (canUse(candidate)) {
      return {
        ok: true,
        route,
        requested_executor: "auto",
        selected_executor: candidate,
        reason: "auto_selected_" + candidate,
        code: "ok",
        headless: true,
        requires_ui: false,
      };
    }
  }

  return {
    ok: false,
    route,
    requested_executor: "auto",
    selected_executor: null,
    reason: "no_headless_executor_ready",
    code: "executor_unavailable",
    headless: true,
    requires_ui: false,
  };
}

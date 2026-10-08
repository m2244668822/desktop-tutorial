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
  const requested = String(value || "auto").trim().toLowerCase();
  return EXECUTORS.has(requested) ? requested : "auto";
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

export function routeInboxTask(text, capabilities = {}, env = process.env) {
  const requested = normalizeRequested(contractField(text, "executor"));
  const explicitRoute = String(contractField(text, "route") || "").toLowerCase();
  const mechanical = classifyMechanicalActions(text);
  const route = ROUTES.has(explicitRoute)
    ? explicitRoute
    : mechanical.ok
      ? "mechanical"
      : "agentic";

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

  for (const candidate of [...new Set(order)]) {
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

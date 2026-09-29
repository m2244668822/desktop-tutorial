/**
 * Permission levels aligned with ChatGPT Web MCP 本機檔案執行流程 §4.
 * Deny-by-default for secrets and paths outside workspace_root.
 */

const DENY_NAME_RE =
  /(^|\/|\\)\.env(\.|$)|(^\.|\/|\\)\.ssh(\/|\\|$)|password|keychain|credentials\.json|\.pem$|\.key$/i;

export function riskForTool(toolName) {
  switch (toolName) {
    case "workspace.list":
    case "workspace.search":
    case "workspace.read":
    case "workspace.propose_patch":
    case "runtime.capabilities":
      return "L0";
    case "workspace.create":
    case "trevor.web_search":
    case "runtime.run_test":
      return "L1";
    case "workspace.patch":
    case "workspace.move":
      return "L2";
    case "workspace.trash":
      return "L3";
    case "git.checkpoint":
      return "L1";
    default:
      return "L4";
  }
}

export function needsApproval(level) {
  return level === "L2" || level === "L3" || level === "L4";
}

export function assertAllowedPath(workspaceRoot, targetPath) {
  const root = workspaceRoot.replace(/\\/g, "/").replace(/\/+$/, "");
  const resolved = targetPath.replace(/\\/g, "/");
  if (!resolved.startsWith(root + "/") && resolved !== root) {
    const err = new Error("path_outside_workspace");
    err.code = "path_outside_workspace";
    throw err;
  }
  if (DENY_NAME_RE.test(resolved)) {
    const err = new Error("path_denied_by_policy");
    err.code = "path_denied_by_policy";
    throw err;
  }
}

export function assertApproval(level, approval) {
  if (!needsApproval(level)) return;
  if (!approval || approval.approved !== true) {
    const err = new Error("approval_required");
    err.code = "approval_required";
    err.level = level;
    throw err;
  }
  if (!approval.action_id || !approval.diff_hash) {
    const err = new Error("approval_incomplete");
    err.code = "approval_incomplete";
    throw err;
  }
  if (approval.expires_at && Date.parse(approval.expires_at) < Date.now()) {
    const err = new Error("approval_expired");
    err.code = "approval_expired";
    throw err;
  }
}

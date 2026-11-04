import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { resolveExecutorCommand } from "../../vault_workspace_mcp/src/workspace.js";

function defaultLocate(command) {
  const locator = process.platform === "win32" ? "where.exe" : "which";
  const result = spawnSync(locator, [command], {
    encoding: "utf8",
    timeout: 2500,
    shell: false,
  });
  return result.status === 0
    ? String(result.stdout || "")
      .split(/\r?\n/)
      .map((item) => item.trim())
      .find(Boolean) || ""
    : "";
}

function overrideFor(command, env) {
  if (command === "codex") return env.WHITE_STUDIO_CODEX_PATH || "";
  if (command === "agent" || command === "cursor") {
    return env.WHITE_STUDIO_CURSOR_AGENT_PATH || "";
  }
  return "";
}

export function resolveToolInvocation(
  command,
  args = [],
  env = process.env,
  locate = defaultLocate,
  exists = fs.existsSync,
) {
  const resolution = resolveExecutorCommand(
    command,
    overrideFor(command, env),
    locate,
    exists,
  );
  const resolvedPath = resolution.path;
  const isBatchShim = process.platform === "win32" && /\.(?:cmd|bat)$/i.test(resolvedPath);

  if (!resolvedPath && resolution.source === "explicit_override_invalid") {
    return {
      source: resolution.source,
      reason: resolution.reason,
      executable: "",
      args: [],
      resolvedPath: "",
    };
  }

  return {
    source: resolution.source,
    executable: isBatchShim
      ? (env.ComSpec || "cmd.exe")
      : (resolvedPath || command),
    args: isBatchShim
      ? ["/d", "/s", "/c", resolvedPath, ...args]
      : args,
    resolvedPath,
  };
}

import fs from "node:fs";
import path from "node:path";

const SERVER_RELATIVE_PATH = path.join(
  "services",
  "vault_workspace_mcp",
  "src",
  "server.js",
);

function candidatePath(root) {
  if (typeof root !== "string" || !root.trim()) return "";
  return path.join(path.resolve(root), SERVER_RELATIVE_PATH);
}

export function resolveMcpServerPath({
  sourceRepoRoot = "",
  worktreeRoot = "",
  runtimeRoot = "",
} = {}) {
  const candidates = [
    candidatePath(runtimeRoot),
    candidatePath(worktreeRoot),
    candidatePath(sourceRepoRoot),
  ].filter(Boolean);

  return candidates.find((candidate) => fs.existsSync(candidate)) ||
    candidatePath(worktreeRoot) ||
    candidatePath(sourceRepoRoot);
}

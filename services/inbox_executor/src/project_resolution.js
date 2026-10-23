import path from "node:path";

export function resolveProjectRelativePath(project, workspaceName) {
  const raw = String(project || "").trim();
  if (raw === "desktop-tutorial") return "runtime/desktop-tutorial";
  if (raw === "automation-fixture") return "runtime/.mcp-automation-fixture";
  if (raw === "." || raw === workspaceName) return ".";
  return raw;
}

export function resolveProjectPath(vaultRoot, project, workspaceName = path.basename(vaultRoot)) {
  const relativePath = resolveProjectRelativePath(project, workspaceName);
  const abs = path.resolve(vaultRoot, relativePath);
  const relative = path.relative(vaultRoot, abs);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw Object.assign(new Error("project_outside_workspace"), { code: "project_outside_workspace" });
  }
  return { name: String(project || "").trim(), vaultRelative: relativePath.replace(/\\/g, "/"), abs };
}

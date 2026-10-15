export function normalizeProjectReference(project, workspaceName) {
  const raw = String(project || "").trim();
  if (!raw) return { name: "", vaultRelative: "" };

  // Contracts may use a human label followed by the executable project key:
  // "Display name / project-key". Keep the key for filesystem and test-profile
  // lookup while retaining a stable name for result evidence.
  const reference = raw.split(/\s+\/\s+/).at(-1)?.trim() || raw;
  if (reference === "desktop-tutorial") {
    return { name: "desktop-tutorial", vaultRelative: "runtime/desktop-tutorial" };
  }
  if (reference === "." || reference === workspaceName) {
    return { name: workspaceName, vaultRelative: "." };
  }
  return { name: reference, vaultRelative: reference.replace(/\\/g, "/") };
}

function classifyError(value) {
  const text = String(value || "");
  if (/approval|requires confirmation|not trusted|untrusted/i.test(text)) return "approval_or_trust";
  if (/timed? ?out|etimedout/i.test(text)) return "timeout";
  if (/schema|invalid (?:argument|parameters)/i.test(text)) return "invalid_tool_contract";
  if (/not (?:available|found|exposed)|unknown tool|no .*tools/i.test(text)) return "tool_unavailable";
  if (/failed to|error|cannot|could not|refus/i.test(text)) return "other_error";
  return "none";
}

const fixtureTools = ["workspace_list", "runtime_capabilities", "workspace_read", "runtime_run_test"];

export function inspectRtsAgentEvents(stdout, stderr) {
  const calls = [];
  let final = "";
  let errors = new Set();
  for (const line of String(stdout || "").split(/\r?\n/)) {
    let event;
    try { event = JSON.parse(line); } catch { continue; }
    if (event.type === "error" || event.type === "turn.failed") {
      errors.add(classifyError(event.message || event.error?.message));
    }
    const item = event.item;
    if (!item) continue;
    if (event.type === "item.completed" && item.type === "agent_message") {
      final = typeof item.text === "string" ? item.text : "";
    }
    if (item.type !== "mcp_tool_call" || !["item.started", "item.completed"].includes(event.type)) continue;
    calls.push({
      server: item.server === "vault-workspace" ? "vault-workspace" : "other",
      tool: fixtureTools.includes(item.tool) ? item.tool : "other",
      stage: event.type === "item.started" ? "attempt" : item.status === "completed" && !item.error ? "completed" : "failed",
      error: classifyError(item.error?.message),
    });
  }
  errors.add(classifyError(stderr));
  errors.delete("none");
  return { final, calls, errors: [...errors], final_hint: classifyError(final) };
}

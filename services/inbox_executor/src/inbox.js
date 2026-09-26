import fs from "node:fs";
import path from "node:path";

const STATUS_RE = /^status:\s*(\w+)\s*$/m;

export function readInbox(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  const m = text.match(STATUS_RE);
  return {
    text,
    status: m ? m[1] : "unknown",
  };
}

export function setStatus(text, status) {
  if (STATUS_RE.test(text)) {
    return text.replace(STATUS_RE, `status: ${status}`);
  }
  // insert after first ---
  return text.replace(/^---\n/, `---\nstatus: ${status}\n`);
}

/**
 * Extract ```json ... ``` under ## Mechanical Actions (or ## 機械動作)
 */
export function extractMechanicalActions(text) {
  const sectionRe =
    /##\s*(Mechanical Actions|機械動作)\s*\n([\s\S]*?)(?=\n##\s|\n#\s|$)/i;
  const section = text.match(sectionRe);
  if (!section) return null;
  const body = section[2];
  const fence = body.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (!fence) return null;
  try {
    const parsed = JSON.parse(fence[1].trim());
    if (!parsed || typeof parsed !== "object") return null;
    if (!Array.isArray(parsed.actions)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function upsertDaemonResult(text, resultMarkdown) {
  const marker = "## Result（inbox-daemon 回寫）";
  const block = `${marker}\n\n${resultMarkdown.trim()}\n`;
  if (text.includes(marker)) {
    return text.replace(
      /## Result（inbox-daemon 回寫）[\s\S]*?(?=\n## (?!Result)|$)/,
      block + "\n"
    );
  }
  // append before last Links if present, else end
  if (/\n## Links\n/.test(text)) {
    return text.replace(/\n## Links\n/, `\n${block}\n## Links\n`);
  }
  return text.trimEnd() + "\n\n" + block + "\n";
}

export function resolveInboxPath(vaultRoot) {
  return path.join(vaultRoot, "智能體", "chatgpt-inbox.md");
}

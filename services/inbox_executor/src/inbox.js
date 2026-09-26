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

/**
 * Archive stale human/Cursor Result so frontmatter status + daemon Result
 * are the only "current" signals (observability hygiene).
 */
export function archiveStaleResult(text) {
  const cursorMarker = "## Result（Cursor 回寫）";
  if (!text.includes(cursorMarker)) return text;
  const histMarker = "## History（archived Result）";
  const extracted = text.match(
    /## Result（Cursor 回寫）\n([\s\S]*?)(?=\n## (?!Result)|$)/
  );
  if (!extracted) return text;
  const body = extracted[1].trim();
  let next = text.replace(
    /## Result（Cursor 回寫）[\s\S]*?(?=\n## (?!Result)|$)/,
    ""
  );
  const entry = `### archived ${new Date().toISOString()}\n\n${body}\n`;
  if (next.includes(histMarker)) {
    next = next.replace(histMarker, `${histMarker}\n\n${entry}`);
  } else if (/\n## Links\n/.test(next)) {
    next = next.replace(/\n## Links\n/, `\n${histMarker}\n\n${entry}\n## Links\n`);
  } else {
    next = next.trimEnd() + `\n\n${histMarker}\n\n${entry}\n`;
  }
  return next;
}

export function upsertDaemonResult(text, resultMarkdown) {
  let next = archiveStaleResult(text);
  const marker = "## Result（inbox-daemon 回寫）";
  const block = `${marker}\n\n${resultMarkdown.trim()}\n`;
  if (next.includes(marker)) {
    return next.replace(
      /## Result（inbox-daemon 回寫）[\s\S]*?(?=\n## (?!Result)|$)/,
      block + "\n"
    );
  }
  if (/\n## Links\n/.test(next)) {
    return next.replace(/\n## Links\n/, `\n${block}\n## Links\n`);
  }
  return next.trimEnd() + "\n\n" + block + "\n";
}

export function resolveInboxPath(vaultRoot) {
  return path.join(vaultRoot, "智能體", "chatgpt-inbox.md");
}

import crypto from "node:crypto";
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

export function contractHash(text) {
  const normalized = text.replace(STATUS_RE, "status: queued");
  return crypto.createHash("sha256").update(normalized, "utf8").digest("hex");
}

export function taskIdFromText(text) {
  return text.match(/task_id\s+([^\s\n]+)/)?.[1] ?? "unknown";
}

/**
 * JSON object slice that ignores braces and backticks inside strings.
 * Contract fence ``` inside a string must not end the contract.
 */
function balancedJsonObject(text, start) {
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (c === "\\") {
        esc = true;
        continue;
      }
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

/**
 * @returns {{ ok: true, code: "ok", parsed: object } | { ok: false, code: "missing_actions" | "parse_error", message?: string }}
 */
export function classifyMechanicalActions(text) {
  const heading = text.search(/^##\s*(Mechanical Actions|機械動作)\s*$/m);
  if (heading < 0) {
    return { ok: false, code: "missing_actions", message: "no Mechanical Actions heading" };
  }
  const after = text.slice(heading);
  const fence = after.match(/```json[^\n]*\n/);
  if (!fence) {
    return { ok: false, code: "missing_actions", message: "no json fence" };
  }
  const jsonStart = after.indexOf("{", fence.index + fence[0].length);
  if (jsonStart < 0) {
    return { ok: false, code: "parse_error", message: "json object missing" };
  }
  const raw = balancedJsonObject(after, jsonStart);
  if (!raw) {
    return { ok: false, code: "parse_error", message: "unbalanced json" };
  }
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.actions)) {
      return { ok: false, code: "parse_error", message: "actions missing" };
    }
    return { ok: true, code: "ok", parsed };
  } catch (err) {
    return { ok: false, code: "parse_error", message: err.message };
  }
}

export function extractMechanicalActions(text) {
  const found = classifyMechanicalActions(text);
  return found.ok ? found.parsed : null;
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

function topLevelSectionRanges(text, heading) {
  const ranges = [];
  let inFence = false;
  for (const match of text.matchAll(/^.*$/gm)) {
    const line = match[0].replace(/\r$/, "");
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence || !line.startsWith("## ")) continue;
    const open = ranges.at(-1);
    if (open && open.end == null) open.end = match.index;
    if (line === heading) ranges.push({ start: match.index, end: null });
  }
  const open = ranges.at(-1);
  if (open && open.end == null) open.end = text.length;
  return ranges;
}

export function upsertDaemonResult(text, resultMarkdown) {
  let next = archiveStaleResult(text);
  const marker = "## Result（inbox-daemon 回寫）";
  const block = `${marker}\n\n${resultMarkdown.trim()}\n`;
  const ranges = topLevelSectionRanges(next, marker);
  if (ranges.length > 0) {
    let cursor = 0;
    let reconciled = "";
    ranges.forEach((range, index) => {
      reconciled += next.slice(cursor, range.start);
      if (index === 0) reconciled += block + "\n";
      cursor = range.end;
    });
    return reconciled + next.slice(cursor);
  }
  if (/\n## Links\n/.test(next)) {
    return next.replace(/\n## Links\n/, `\n${block}\n## Links\n`);
  }
  return next.trimEnd() + "\n\n" + block + "\n";
}

export function resolveInboxPath(vaultRoot) {
  return path.join(vaultRoot, "智能體", "chatgpt-inbox.md");
}

import fs from "node:fs";
import path from "node:path";

function ledgerPath(vaultRoot) {
  return path.join(vaultRoot, "runtime", ".inbox-attempts.json");
}

export function readLedger(vaultRoot) {
  const file = ledgerPath(vaultRoot);
  if (!fs.existsSync(file)) return { tasks: {} };
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
    if (!parsed || typeof parsed !== "object") return { tasks: {} };
    if (!parsed.tasks || typeof parsed.tasks !== "object") parsed.tasks = {};
    return parsed;
  } catch {
    return { tasks: {} };
  }
}

export function writeLedger(vaultRoot, ledger) {
  const file = ledgerPath(vaultRoot);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(ledger, null, 2), "utf8");
}

export function lookupAttempt(vaultRoot, taskId) {
  if (!taskId) return null;
  return readLedger(vaultRoot).tasks[taskId] || null;
}

export function recordAttempt(vaultRoot, taskId, entry) {
  const ledger = readLedger(vaultRoot);
  const prev = ledger.tasks[taskId] || {};
  const same = prev.hash && prev.hash === entry.hash;
  ledger.tasks[taskId] = {
    ...prev,
    ...entry,
    attempts: same ? (prev.attempts || 0) + 1 : 1,
    updated: new Date().toISOString(),
  };
  writeLedger(vaultRoot, ledger);
  return ledger.tasks[taskId];
}

export function patchAttempt(vaultRoot, taskId, patch) {
  const ledger = readLedger(vaultRoot);
  const prev = ledger.tasks[taskId];
  if (!prev) return null;
  ledger.tasks[taskId] = { ...prev, ...patch, updated: new Date().toISOString() };
  writeLedger(vaultRoot, ledger);
  return ledger.tasks[taskId];
}

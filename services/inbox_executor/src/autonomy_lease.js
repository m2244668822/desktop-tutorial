import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

function defaultDataRoot() {
  if (process.env.TREVOR_DATA_DIR) return path.resolve(process.env.TREVOR_DATA_DIR);
  if (process.platform === "win32") {
    return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "Trevor");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "Trevor");
  }
  return path.join(os.homedir(), ".local", "share", "trevor");
}

export function defaultAutonomyRoot(vaultRoot) {
  return path.resolve(
    process.env.WHITE_STUDIO_AUTONOMY_ROOT || path.join(defaultDataRoot(), "autonomy")
  );
}

function nowMs() {
  return Date.now();
}

function readLease(leasePath) {
  try {
    const payload = JSON.parse(fs.readFileSync(leasePath, "utf8"));
    return payload && typeof payload === "object" ? payload : {};
  } catch {
    return {};
  }
}

export function createAutonomyLease({ root, owner, ttlSeconds = 1800 }) {
  const leasePath = path.join(path.resolve(root), "task.lease");
  const leaseOwner = String(owner || "").trim();
  const ttlMs = Math.max(60, Number(ttlSeconds) || 1800) * 1000;
  let current = null;

  function acquire() {
    if (!leaseOwner) throw new Error("lease_owner_required");
    fs.mkdirSync(path.dirname(leasePath), { recursive: true });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const acquired = new Date(nowMs());
      const payload = {
        owner: leaseOwner,
        lease_id: crypto.randomBytes(16).toString("hex"),
        acquired_at: acquired.toISOString(),
        expires_at: new Date(nowMs() + ttlMs).toISOString(),
      };
      try {
        const fd = fs.openSync(leasePath, "wx", 0o600);
        try {
          fs.writeFileSync(fd, `${JSON.stringify(payload)}\n`, "utf8");
          fs.fsyncSync(fd);
        } finally {
          fs.closeSync(fd);
        }
        current = payload;
        return true;
      } catch (error) {
        if (error?.code !== "EEXIST") throw error;
        const existing = readLease(leasePath);
        const expiry = Date.parse(String(existing.expires_at || ""));
        if (Number.isFinite(expiry) && expiry > nowMs()) return false;
        try {
          fs.unlinkSync(leasePath);
        } catch {
          return false;
        }
      }
    }
    return false;
  }

  function release() {
    if (!current) return false;
    const existing = readLease(leasePath);
    if (existing.owner !== leaseOwner || existing.lease_id !== current.lease_id) return false;
    try {
      fs.unlinkSync(leasePath);
      current = null;
      return true;
    } catch {
      return false;
    }
  }

  return { path: leasePath, acquire, release };
}

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

function errorCode(error) {
  return error?.code || error?.name || "unknown";
}

function assertTempTarget(root, tempRoot) {
  const base = path.resolve(tempRoot);
  const target = path.resolve(root);
  if (target === base || !target.startsWith(`${base}${path.sep}`)) {
    throw new Error(`cleanup_target_outside_temp_root:${target}`);
  }
  return { base, target };
}

function quarantinePath(target, base, name) {
  const filename = name || `${path.basename(target)}.quarantine-${Date.now()}-${crypto.randomUUID()}`;
  const candidate = path.resolve(base, filename);
  if (candidate === base || !candidate.startsWith(`${base}${path.sep}`)) {
    throw new Error(`cleanup_quarantine_outside_temp_root:${candidate}`);
  }
  return candidate;
}

/**
 * Remove a disposable temp tree without turning a Windows sharing race into a
 * false workflow failure. If bounded retry cannot remove it, quarantine it in
 * the same temp parent and return evidence. A quarantine failure is fatal.
 */
export function cleanupTempRoot(root, {
  fsImpl = fs,
  tempRoot = os.tmpdir(),
  maxRetries = 5,
  retryDelay = 250,
  quarantineName,
} = {}) {
  const { base, target } = assertTempTarget(root, tempRoot);
  try {
    fsImpl.rmSync(target, {
      recursive: true,
      force: true,
      maxRetries,
      retryDelay,
    });
    return { status: "removed", path: target, attempts: maxRetries + 1 };
  } catch (error) {
    const quarantine = quarantinePath(target, base, quarantineName);
    try {
      fsImpl.renameSync(target, quarantine);
      return {
        status: "quarantined",
        path: quarantine,
        source: target,
        error_code: errorCode(error),
      };
    } catch (quarantineError) {
      const failure = new Error(
        `cleanup_failed:${errorCode(error)}:${errorCode(quarantineError)}`
      );
      failure.cause = error;
      failure.quarantineError = quarantineError;
      throw failure;
    }
  }
}

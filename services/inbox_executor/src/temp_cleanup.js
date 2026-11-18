import crypto from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

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

function retryableCleanupError(error) {
  return new Set(["EACCES", "EBUSY", "ENOTEMPTY", "EPERM"]).has(errorCode(error));
}

function waitMs(milliseconds) {
  if (milliseconds <= 0) return;
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

function scheduleDeferredCleanup(target, base, {
  fsImpl,
  spawnImpl = spawn,
  maxRetries,
  retryDelay,
} = {}) {
  const helper = path.join(path.dirname(fileURLToPath(import.meta.url)), "deferred_cleanup.js");
  const child = spawnImpl(
    process.execPath,
    [helper, target, base, String(maxRetries), String(retryDelay)],
    { detached: true, stdio: "ignore", windowsHide: true }
  );
  if (!child || typeof child.unref !== "function") {
    throw new Error("cleanup_deferred_helper_not_started");
  }
  child.unref();
  return child.pid || "unknown";
}

/**
 * Remove a disposable temp tree without turning a Windows sharing race into a
 * false workflow failure. If bounded retry cannot remove it, quarantine it in
 * the same temp parent and return evidence. If Windows still holds a sharing
 * handle, schedule a bounded post-exit cleanup and report that state clearly.
 */
export function cleanupTempRoot(root, {
  fsImpl = fs,
  tempRoot = os.tmpdir(),
  maxRetries = 5,
  retryDelay = 250,
  quarantineName,
  spawnImpl = spawn,
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
    let quarantineError;
    for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
      try {
        fsImpl.renameSync(target, quarantine);
        return {
          status: "quarantined",
          path: quarantine,
          source: target,
          error_code: errorCode(error),
          rename_attempts: attempt + 1,
        };
      } catch (candidateError) {
        quarantineError = candidateError;
        if (!retryableCleanupError(candidateError) || attempt === maxRetries) break;
        waitMs(retryDelay);
      }
    }

    if (retryableCleanupError(error) && retryableCleanupError(quarantineError)) {
      try {
        return {
          status: "deferred",
          path: target,
          source: target,
          quarantine_path: quarantine,
          error_code: errorCode(error),
          quarantine_error_code: errorCode(quarantineError),
          cleanup_pid: scheduleDeferredCleanup(target, base, {
            fsImpl,
            spawnImpl,
            maxRetries,
            retryDelay,
          }),
        };
      } catch (deferredError) {
        const failure = new Error(
          `cleanup_failed:${errorCode(error)}:${errorCode(quarantineError)}:${errorCode(deferredError)}`
        );
        failure.cause = error;
        failure.quarantineError = quarantineError;
        failure.deferredError = deferredError;
        throw failure;
      }
    }

    const failure = new Error(`cleanup_failed:${errorCode(error)}:${errorCode(quarantineError)}`);
    failure.cause = error;
    failure.quarantineError = quarantineError;
    throw failure;
  }
}

import assert from "node:assert/strict";
import test from "node:test";

import { cleanupTempRoot } from "./temp_cleanup.js";

const tempRoot = "C:\\Users\\m2244\\AppData\\Local\\Temp";

test("cleanupTempRoot enables bounded Windows retry", () => {
  const calls = [];
  const result = cleanupTempRoot(`${tempRoot}\\queue-e2e-pass`, {
    fsImpl: {
      rmSync(target, options) {
        calls.push({ target, options });
      },
    },
    tempRoot,
  });

  assert.equal(result.status, "removed");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.maxRetries, 5);
  assert.equal(calls[0].options.retryDelay, 250);
});

test("cleanupTempRoot quarantines a persistently locked directory", () => {
  const calls = [];
  const result = cleanupTempRoot(`${tempRoot}\\queue-e2e-locked`, {
    fsImpl: {
      rmSync() {
        const error = new Error("locked");
        error.code = "EPERM";
        throw error;
      },
      renameSync(source, target) {
        calls.push({ source, target });
      },
    },
    tempRoot,
    quarantineName: "queue-e2e-locked.quarantine",
  });

  assert.equal(result.status, "quarantined");
  assert.equal(result.path, `${tempRoot}\\queue-e2e-locked.quarantine`);
  assert.deepEqual(calls, [{
    source: `${tempRoot}\\queue-e2e-locked`,
    target: `${tempRoot}\\queue-e2e-locked.quarantine`,
  }]);
});

test("cleanupTempRoot rejects a cleanup target outside the temp root", () => {
  assert.throws(
    () => cleanupTempRoot("C:\\Users\\m2244\\Desktop\\outside", { tempRoot }),
    /cleanup_target_outside_temp_root/
  );
});

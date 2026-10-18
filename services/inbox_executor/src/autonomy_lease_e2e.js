import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createAutonomyLease } from "./autonomy_lease.js";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "white-studio-lease-"));
const first = createAutonomyLease({ root, owner: "first", ttlSeconds: 60 });
const second = createAutonomyLease({ root, owner: "second", ttlSeconds: 60 });

try {
  if (!first.acquire()) throw new Error("first_acquire_failed");
  if (second.acquire()) throw new Error("second_acquire_should_be_blocked");
  if (!first.release()) throw new Error("first_release_failed");
  if (!second.acquire()) throw new Error("second_reacquire_failed");
  if (!second.release()) throw new Error("second_release_failed");
  console.log("AUTONOMY_LEASE_E2E_PASS");
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}

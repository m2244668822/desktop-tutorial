import { parentPort, workerData } from "node:worker_threads";
import { heartbeatLease } from "./transaction.js";

let active = true;
let lease = workerData.lease;

function beat() {
  if (!active) return;
  try {
    lease = heartbeatLease({
      storePath: workerData.storePath,
      lease,
      ttlMs: workerData.ttlMs,
    });
  } catch (error) {
    parentPort.postMessage({ type: "error", code: error.code || "lease_heartbeat_failed" });
    active = false;
  }
}

const timer = setInterval(beat, workerData.intervalMs);
parentPort.on("message", (message) => {
  if (message?.type === "stop") {
    active = false;
    clearInterval(timer);
    process.exit(0);
  }
});

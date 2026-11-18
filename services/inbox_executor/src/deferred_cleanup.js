import fs from "node:fs";
import path from "node:path";

const [, , targetArg, baseArg, maxRetriesArg = "5", retryDelayArg = "250"] = process.argv;
const target = path.resolve(targetArg || "");
const base = path.resolve(baseArg || "");
const maxRetries = Number.parseInt(maxRetriesArg, 10);
const retryDelay = Number.parseInt(retryDelayArg, 10);

if (!target || !base || target === base || !target.startsWith(`${base}${path.sep}`)) {
  process.exit(2);
}

function waitMs(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
  try {
    fs.rmSync(target, { recursive: true, force: true, maxRetries, retryDelay });
    process.exit(0);
  } catch (error) {
    if (!["EACCES", "EBUSY", "ENOTEMPTY", "EPERM"].includes(error?.code)) {
      process.exit(1);
    }
    if (attempt === maxRetries) process.exit(1);
    await waitMs(retryDelay);
  }
}

import fs from "node:fs";
import { loadEvidenceInputs, verifyRecordedEvidence } from "./high_automation_evidence.js";

try {
  const { inputs, outputPath } = loadEvidenceInputs();
  let record = null;
  try {
    record = JSON.parse(fs.readFileSync(outputPath, "utf8"));
  } catch {
    // The verifier reports a missing or unreadable record as NOT_READY.
  }
  const result = verifyRecordedEvidence(record, inputs);
  console.log(JSON.stringify(result));
  process.exitCode = result.ready ? 0 : 1;
} catch (error) {
  console.error(error.message);
  process.exitCode = 2;
}

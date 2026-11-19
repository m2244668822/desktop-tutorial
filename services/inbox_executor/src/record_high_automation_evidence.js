import { loadEvidenceInputs, recordEvidence } from "./high_automation_evidence.js";

try {
  const { inputs, outputPath } = loadEvidenceInputs();
  const { assessment } = recordEvidence(inputs, outputPath);
  console.log(JSON.stringify({ output: outputPath, recorded: true, reasons: assessment.reasons }));
} catch (error) {
  console.error(error.message);
  process.exitCode = 2;
}

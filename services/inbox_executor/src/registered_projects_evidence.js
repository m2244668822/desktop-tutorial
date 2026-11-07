#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import {
  assertJsonSchema,
  readJsonSchema,
  validateRegisteredProjectsEvidence,
} from "./evidence_schema.js";

export const REGISTERED_PROJECT_IDS = [
  "desktop-tutorial",
  "automation-fixture",
  "white-studio-thunder-arcade",
  "white-studio-web",
  "white-studio-games",
  "white-studio-palette-creator",
  "white-studio-game-contributor-kit",
  "partner-site-demo",
];

const MAX_TIMEOUT_SEC = 120;

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function relativePath(root, target) {
  return path.relative(root, target).replace(/\\/g, "/");
}

function isInside(root, target) {
  const rel = path.relative(root, target);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

function projectRootPath(repoRoot, projectRoot) {
  const lexical = path.resolve(repoRoot, projectRoot || "");
  if (!isInside(repoRoot, lexical)) return { path: lexical, safe: false };
  if (!fs.existsSync(lexical)) return { path: lexical, safe: true };
  const realRepo = fs.realpathSync(repoRoot);
  const realRoot = fs.realpathSync(lexical);
  return { path: realRoot, safe: isInside(realRepo, realRoot) };
}

function boundedTimeout(value) {
  const timeout = Number(value);
  if (!Number.isInteger(timeout) || timeout < 1 || timeout > MAX_TIMEOUT_SEC) return 0;
  return timeout;
}

function sanitizedResult({ test, result, errorCode = "" }) {
  const timedOut = Boolean(result?.timed_out) || errorCode === "test_timeout";
  const ok = Boolean(result?.ok) && !timedOut;
  return {
    runner: String(test.runner || ""),
    target: String(test.target || ""),
    timeout_sec: boundedTimeout(test.timeoutSec) || 1,
    status: timedOut ? "timeout" : ok ? "pass" : "fail",
    ok,
    timed_out: timedOut,
    exit_code: Number.isInteger(result?.exit_code) ? result.exit_code : null,
    ...(errorCode ? { error_code: errorCode } : {}),
  };
}

function sourceSnapshotFromManifest(repoRoot) {
  const manifestPath = path.join(
    repoRoot,
    "runtime",
    ".mcp-automation-fixture",
    "rts01-high-automation-evidence-20261107-r4.json",
  );
  if (!fs.existsSync(manifestPath)) return "";
  try {
    return String(JSON.parse(fs.readFileSync(manifestPath, "utf8"))?.source?.source_snapshot_sha || "");
  } catch {
    return "";
  }
}

function schemaPath(repoRoot) {
  return path.join(repoRoot, "runtime", ".mcp-state", "registered-projects-evidence.schema.json");
}

export function collectRegisteredProjectsEvidence({
  repoRoot,
  profilesPath = path.join(repoRoot, "runtime", "test-profiles.json"),
  outputPath = "",
  sourceSnapshotSha = sourceSnapshotFromManifest(repoRoot),
  workspaceFactory = (root) => new VaultWorkspace({
    workspaceRoot: root,
    auditDir: path.join(root, "runtime", ".mcp-state", "registered-projects-audit"),
    trashDir: path.join(root, "runtime", ".mcp-state", "registered-projects-trash"),
    autoApprove: false,
  }),
} = {}) {
  const absoluteRepoRoot = path.resolve(repoRoot || "");
  if (!absoluteRepoRoot || !fs.existsSync(absoluteRepoRoot)) throw new Error("registered_projects_repo_missing");
  if (!sourceSnapshotSha) throw new Error("source_snapshot_sha_missing");
  const profiles = JSON.parse(fs.readFileSync(profilesPath, "utf8"));
  const profileHash = sha256File(profilesPath);
  const profilePath = relativePath(absoluteRepoRoot, path.resolve(profilesPath));
  const workspace = workspaceFactory(absoluteRepoRoot);
  const reasons = [];
  const records = [];

  for (const projectId of REGISTERED_PROJECT_IDS) {
    const profile = profiles.projects?.[projectId];
    const record = {
      project_id: projectId,
      root: String(profile?.root || ""),
      profile_sha256: profileHash,
      source_scope: profilePath,
      root_exists: false,
      fixed_tests: [],
      status: "fail",
    };
    if (!profile || profile.automation_mode !== "bounded_write") {
      record.fixed_tests = [{
        runner: "",
        target: "",
        timeout_sec: 1,
        status: "blocked",
        ok: false,
        timed_out: false,
        error_code: "registered_project_profile_missing_or_not_bounded",
      }];
      reasons.push("registered_project_profile_missing");
      records.push(record);
      continue;
    }

    const rootInfo = projectRootPath(absoluteRepoRoot, profile.root);
    record.root_exists = rootInfo.safe && fs.existsSync(rootInfo.path) && fs.statSync(rootInfo.path).isDirectory();
    if (!record.root_exists) {
      record.fixed_tests = (Array.isArray(profile.tests) ? profile.tests : []).map((test) => sanitizedResult({
        test,
        errorCode: rootInfo.safe ? "registered_project_root_missing" : "registered_project_root_unsafe",
      }));
      if (record.fixed_tests.length === 0) record.fixed_tests.push({
        runner: "",
        target: "",
        timeout_sec: 1,
        status: "blocked",
        ok: false,
        timed_out: false,
        error_code: rootInfo.safe ? "registered_project_root_missing" : "registered_project_root_unsafe",
      });
      reasons.push(rootInfo.safe ? "registered_project_root_missing" : "registered_project_root_unsafe");
      records.push(record);
      continue;
    }

    if (!Array.isArray(profile.tests) || profile.tests.length === 0) {
      record.fixed_tests = [{
        runner: "",
        target: "",
        timeout_sec: 1,
        status: "blocked",
        ok: false,
        timed_out: false,
        error_code: "registered_project_fixed_tests_missing",
      }];
      reasons.push("registered_project_fixed_test_missing");
      records.push(record);
      continue;
    }

    for (const test of profile.tests) {
      const timeoutSec = boundedTimeout(test.timeoutSec);
      if (!timeoutSec) {
        record.fixed_tests.push(sanitizedResult({ test, errorCode: "registered_project_timeout_invalid" }));
        reasons.push("registered_project_fixed_test_failed");
        continue;
      }
      try {
        const result = workspace.runTest({
          runner: test.runner,
          target: test.target,
          projectDir: profile.root,
          timeoutSec,
        });
        const sanitized = sanitizedResult({ test, result });
        record.fixed_tests.push(sanitized);
        if (!sanitized.ok) reasons.push("registered_project_fixed_test_failed");
      } catch (error) {
        const code = String(error?.code || "test_execution_error");
        const sanitized = sanitizedResult({ test, errorCode: code });
        record.fixed_tests.push(sanitized);
        reasons.push(code === "test_project_missing" ? "registered_project_root_missing" : "registered_project_fixed_test_failed");
      }
    }
    record.status = record.root_exists && record.fixed_tests.length > 0 && record.fixed_tests.every((item) => item.status === "pass") ? "pass" : "fail";
    records.push(record);
  }

  const packet = {
    schema_version: 1,
    kind: "registered_projects_evidence",
    generated_at: new Date().toISOString(),
    source_snapshot_sha: sourceSnapshotSha,
    registered_projects: records,
    status: reasons.length === 0 && records.every((record) => record.status === "pass") ? "pass" : "fail",
    reasons: [...new Set(reasons)],
    arbitrary_commands: false,
    writes_forbidden: true,
  };

  validateRegisteredProjectsEvidence(packet, { expectedProjectIds: REGISTERED_PROJECT_IDS });
  const packetSchema = schemaPath(absoluteRepoRoot);
  if (fs.existsSync(packetSchema)) assertJsonSchema(packet, readJsonSchema(packetSchema), "registered_projects");
  if (outputPath) {
    const absoluteOutput = path.resolve(outputPath);
    for (const record of records) {
      const root = path.resolve(absoluteRepoRoot, record.root || "");
      if (record.root && isInside(root, absoluteOutput)) throw new Error("evidence_output_inside_project_root");
    }
    fs.mkdirSync(path.dirname(absoluteOutput), { recursive: true });
    fs.writeFileSync(absoluteOutput, JSON.stringify(packet, null, 2) + "\n", "utf8");
  }
  return packet;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const repoRoot = path.resolve(process.env.VAULT_WORKSPACE_ROOT || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", ".."));
  const outputPath = process.argv.includes("--output") ? process.argv[process.argv.indexOf("--output") + 1] : path.join(repoRoot, "runtime", ".mcp-state", "registered-projects-evidence.json");
  const packet = collectRegisteredProjectsEvidence({ repoRoot, outputPath, sourceSnapshotSha: process.env.RTS01_SOURCE_SNAPSHOT_SHA || undefined });
  process.stdout.write(JSON.stringify({ output: outputPath, status: packet.status, reasons: packet.reasons }, null, 2) + "\n");
  if (packet.status !== "pass") process.exitCode = 1;
}

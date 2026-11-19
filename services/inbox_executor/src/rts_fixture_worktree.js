import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, realpathSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const fixture = "runtime/.mcp-automation-fixture";
const fixtureTest = fixture + "/tests/fixture.test.js";
const worktreeTimeoutMs = 180000;

function probe(cwd, args, timeout = worktreeTimeoutMs) {
  const started = Date.now();
  const result = spawnSync("git", ["-c", "core.longpaths=true", ...args],
    { cwd, encoding: "utf8", timeout, windowsHide: true, maxBuffer: 8 * 1024 * 1024 });
  return {
    result,
    elapsed_ms: Date.now() - started,
    exit_code: result.status,
    error_code: result.error?.code ?? null,
  };
}

function checked(cwd, args, phase, timeout) {
  const { result, ...evidence } = probe(cwd, args, timeout);
  if (result.status !== 0) {
    const code = evidence.error_code === "ETIMEDOUT" ? "worktree_create_timeout" : "worktree_create_failed";
    throw Object.assign(new Error(code), { code, worktreeEvidence: { phase, ...evidence } });
  }
  return result.stdout.trim();
}

export function createRtsFixtureWorktree(source, target, sha) {
  const started = Date.now();
  checked(source, ["worktree", "add", "--detach", "--no-checkout", target, sha], "register");
  checked(target, ["sparse-checkout", "set", "--no-cone", "--", "/" + fixture + "/**"], "sparse_config");
  checked(target, ["read-tree", "-mu", "HEAD"], "materialize");
  const actualSha = checked(target, ["rev-parse", "HEAD"], "verify_revision");
  const tracked = checked(target, ["ls-files", "-t"], "verify_scope").split(/\r?\n/);
  const materialized = tracked.filter(line => !line.startsWith("S ")).map(line => line.slice(2));
  if (actualSha !== sha || !materialized.includes(fixtureTest) ||
      materialized.some(file => !file.startsWith(fixture + "/")) ||
      !existsSync(path.join(target, fixtureTest)) || existsSync(path.join(target, "AGENTS.md")) ||
      checked(target, ["status", "--porcelain", "--untracked-files=all"], "verify_clean")) {
    throw Object.assign(new Error("worktree_scope_invalid"), { code: "worktree_scope_invalid" });
  }
  return { mode: "fixture_sparse", elapsed_ms: Date.now() - started, sha, materialized_count: materialized.length };
}

function runDiagnostic(source, sha, mode) {
  const scratch = mkdtempSync(path.join(process.env.RUNNER_TEMP || tmpdir(), "r23-wt-"));
  const target = path.join(scratch, "checkout");
  try {
    if (mode === "compare") {
      const { result, ...evidence } = probe(source, ["worktree", "add", "--detach", target, sha]);
      console.log("RTS01_WORKTREE_BASELINE " + JSON.stringify({ ...evidence, limit_ms: worktreeTimeoutMs }));
      if (result.status === 0) {
        if (!existsSync(path.join(target, fixtureTest))) throw new Error("baseline fixture missing");
      } else if (evidence.error_code !== "ETIMEDOUT") {
        throw new Error("baseline failed without ETIMEDOUT");
      }
      if (existsSync(path.join(target, ".git"))) {
        checked(source, ["worktree", "remove", "--force", target], "baseline_cleanup");
      }
    }
    console.log("RTS01_WORKTREE_PROBE_PASS " + JSON.stringify(createRtsFixtureWorktree(source, target, sha)));
  } finally {
    if (existsSync(path.join(target, ".git"))) {
      checked(source, ["worktree", "remove", "--force", target], "probe_cleanup");
    }
    rmdirSync(scratch);
  }
  console.log("RTS01_WORKTREE_PROBE_CLEANUP_PASS");
}

if (process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))) {
  const [source, sha, mode] = process.argv.slice(2);
  try {
    if (!source || !/^[0-9a-f]{40}$/.test(sha) || !["compare", "sparse"].includes(mode)) {
      throw new Error("expected source, Git SHA, and compare or sparse");
    }
    runDiagnostic(source, sha, mode);
  } catch (error) {
    console.error("RTS01_WORKTREE_PROBE_BLOCKED " + JSON.stringify({
      code: error.code ?? error.message,
      ...error.worktreeEvidence,
    }));
    process.exitCode = 1;
  }
}

#!/usr/bin/env node
/**
 * Transport layer for Path B:
 *   fetch remote inbox → run inbox-executor once → optional commit/push Result
 *
 * Only touches 智能體/chatgpt-inbox.md. Does not pull the whole dirty vault by default.
 *
 * Env:
 *   VAULT_WORKSPACE_ROOT
 *   INBOX_SYNC_PULL=1   checkout inbox from origin/main before execute
 *   INBOX_SYNC_PUSH=1   commit+push inbox after done/blocked
 *   INBOX_SYNC_REMOTE=origin
 *   INBOX_SYNC_BRANCH=main
 *   INBOX_AUTO_APPROVE  passed through to executor
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readInbox, resolveInboxPath } from "./inbox.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const inboxRel = path.join("智能體", "chatgpt-inbox.md");
const inboxPath = resolveInboxPath(vaultRoot);
const remote = process.env.INBOX_SYNC_REMOTE || "origin";
const branch = process.env.INBOX_SYNC_BRANCH || "main";
const doPull = process.env.INBOX_SYNC_PULL !== "0";
const doPush = process.env.INBOX_SYNC_PUSH === "1";

function log(msg) {
  process.stderr.write(`[inbox-sync] ${new Date().toISOString()} ${msg}\n`);
}

function git(args, opts = {}) {
  const r = spawnSync("git", args, {
    cwd: vaultRoot,
    encoding: "utf8",
    ...opts,
  });
  return r;
}

function mustGit(args) {
  const r = git(args);
  if (r.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${(r.stderr || r.stdout || "").slice(0, 500)}`);
  }
  return r.stdout || "";
}

log(`vault=${vaultRoot}`);
log(`pull=${doPull} push=${doPush} remote=${remote} branch=${branch}`);

// 1) fetch
{
  const r = git(["fetch", remote, branch]);
  if (r.status !== 0) {
    log(`fetch_failed: ${(r.stderr || "").slice(0, 300)}`);
    process.exit(2);
  }
  log("fetch_ok");
}

// 2) checkout remote inbox only (does not merge other files)
if (doPull) {
  const r = git(["checkout", `${remote}/${branch}`, "--", inboxRel]);
  if (r.status !== 0) {
    log(`checkout_inbox_failed: ${(r.stderr || "").slice(0, 300)}`);
    process.exit(3);
  }
  const { status } = readInbox(inboxPath);
  log(`inbox_after_pull status=${status}`);
}

// 3) run executor once (same process tree)
{
  const daemon = path.join(__dirname, "daemon.js");
  const env = {
    ...process.env,
    VAULT_WORKSPACE_ROOT: vaultRoot,
    INBOX_PATH: inboxPath,
  };
  const r = spawnSync(process.execPath, [daemon, "--once"], {
    cwd: path.dirname(daemon),
    env,
    encoding: "utf8",
  });
  if (r.stderr) process.stderr.write(r.stderr);
  if (r.status !== 0) {
    log(`executor_exit=${r.status}`);
    process.exit(r.status || 4);
  }
}

const after = readInbox(inboxPath);
log(`inbox_after_exec status=${after.status}`);

// 4) optional commit + push (inbox only)
if (!doPush) {
  log("push_skipped (set INBOX_SYNC_PUSH=1 to enable)");
  process.exit(0);
}

if (after.status !== "done" && after.status !== "blocked") {
  log(`push_skipped status=${after.status}`);
  process.exit(0);
}

const porcelain = git(["status", "--porcelain", "--", inboxRel]).stdout || "";
if (!porcelain.trim()) {
  log("push_skipped no_local_inbox_diff");
  process.exit(0);
}

const authorName = process.env.GIT_AUTHOR_NAME || "inbox-sync";
const authorEmail =
  process.env.GIT_AUTHOR_EMAIL || "inbox-sync@users.noreply.github.com";
const env = {
  ...process.env,
  GIT_AUTHOR_NAME: authorName,
  GIT_AUTHOR_EMAIL: authorEmail,
  GIT_COMMITTER_NAME: authorName,
  GIT_COMMITTER_EMAIL: authorEmail,
};

mustGit(["add", "--", inboxRel]);
const msg = `inbox-daemon: ${after.status} chatgpt-inbox (${new Date().toISOString()})`;
const commit = spawnSync("git", ["commit", "-m", msg], {
  cwd: vaultRoot,
  encoding: "utf8",
  env,
});
if (commit.status !== 0) {
  log(`commit_failed: ${(commit.stderr || commit.stdout || "").slice(0, 400)}`);
  process.exit(5);
}
log("commit_ok");

// rebase onto remote to reduce non-fast-forward (autostash other dirt)
{
  const pull = spawnSync(
    "git",
    ["pull", "--rebase", "--autostash", remote, branch],
    { cwd: vaultRoot, encoding: "utf8", env }
  );
  if (pull.status !== 0) {
    log(`rebase_failed: ${(pull.stderr || pull.stdout || "").slice(0, 500)}`);
    log("hint: resolve rebase, then push manually; inbox Result is local");
    process.exit(6);
  }
  log("rebase_ok");
}

{
  const push = spawnSync("git", ["push", remote, `HEAD:${branch}`], {
    cwd: vaultRoot,
    encoding: "utf8",
    env,
  });
  if (push.status !== 0) {
    log(`push_failed: ${(push.stderr || push.stdout || "").slice(0, 500)}`);
    process.exit(7);
  }
  log("push_ok");
}

process.exit(0);

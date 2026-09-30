const CLAIM_MARKER = "## Executor Claim";

export const EXECUTOR_IDENTITY_FIELDS = Object.freeze([
  "executor_id",
  "executor_type",
  "executor_provider",
  "executor_product",
  "executor_mode",
  "executor_version",
  "executor_capabilities",
  "claimed_at",
]);

function requiredText(value, field) {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    throw Object.assign(new Error(`executor_identity_missing:${field}`), {
      code: "executor_identity_invalid",
      field,
    });
  }
  return normalized;
}

export function normalizeExecutorIdentity(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw Object.assign(new Error("executor_identity_missing"), {
      code: "executor_identity_invalid",
    });
  }
  const capabilities = raw.executor_capabilities;
  if (!Array.isArray(capabilities)) {
    throw Object.assign(
      new Error("executor_identity_missing:executor_capabilities"),
      { code: "executor_identity_invalid", field: "executor_capabilities" }
    );
  }
  return {
    executor_id: requiredText(raw.executor_id, "executor_id"),
    executor_type: requiredText(raw.executor_type, "executor_type"),
    executor_provider: requiredText(raw.executor_provider, "executor_provider"),
    executor_product: requiredText(raw.executor_product, "executor_product"),
    executor_mode: requiredText(raw.executor_mode, "executor_mode"),
    executor_version: requiredText(raw.executor_version, "executor_version"),
    executor_capabilities: capabilities.map((item) => requiredText(item, "executor_capabilities")),
    claimed_at: requiredText(raw.claimed_at, "claimed_at"),
  };
}

/**
 * The active executor declares its identity. Tool/CLI availability is never
 * used to infer who owns the current claim.
 */
export function executorIdentityFromEnvironment(env = process.env, now = new Date()) {
  if (env.INBOX_EXECUTOR_IDENTITY) {
    let parsed;
    try {
      parsed = JSON.parse(env.INBOX_EXECUTOR_IDENTITY);
    } catch (error) {
      throw Object.assign(new Error(`executor_identity_json_invalid:${error.message}`), {
        code: "executor_identity_invalid",
      });
    }
    return normalizeExecutorIdentity({
      ...parsed,
      claimed_at: parsed.claimed_at || now.toISOString(),
    });
  }

  return normalizeExecutorIdentity({
    executor_id: env.INBOX_EXECUTOR_ID || "inbox-daemon",
    executor_type: env.INBOX_EXECUTOR_TYPE || "local",
    executor_provider: env.INBOX_EXECUTOR_PROVIDER || "white-studio",
    executor_product: env.INBOX_EXECUTOR_PRODUCT || "inbox-executor",
    executor_mode: env.INBOX_EXECUTOR_MODE || "daemon",
    executor_version: env.INBOX_EXECUTOR_VERSION || "0.1.0",
    executor_capabilities: String(
      env.INBOX_EXECUTOR_CAPABILITIES || "mechanical-actions,vault-workspace-mcp"
    )
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    claimed_at: now.toISOString(),
  });
}

export function upsertExecutorClaim(text, taskId, identity) {
  const normalized = normalizeExecutorIdentity(identity);
  const block = `${CLAIM_MARKER}\n\n- task_id：\`${taskId}\`\n- status：\`running\`\n\n\`\`\`json\n${JSON.stringify(normalized, null, 2)}\n\`\`\`\n`;
  const claimPattern = /## Executor Claim(?:（[^）]+）)?[\s\S]*?(?=\n## |$)/;
  if (claimPattern.test(text)) {
    return text.replace(claimPattern, block.trimEnd());
  }
  const resultIndex = text.search(/^## Result/m);
  if (resultIndex >= 0) {
    return `${text.slice(0, resultIndex).trimEnd()}\n\n${block}\n${text.slice(resultIndex)}`;
  }
  return `${text.trimEnd()}\n\n${block}`;
}

export function extractExecutorClaim(text) {
  const block = text
    .split(/(?=^## )/m)
    .find((candidate) => /^## Executor Claim(?:（[^）]+）)?[ \t]*\r?$/m.test(candidate));
  if (!block) return { legacy: true, task_id: null, identity: null };
  const taskId = block.match(/^- task_id：`([^`]+)`/m)?.[1] ?? null;
  const identityJson = block.match(/```json\s*\r?\n([\s\S]*?)\r?\n```/)?.[1];
  if (!taskId || !identityJson) {
    return {
      legacy: false,
      task_id: taskId,
      identity: null,
      error: "executor_identity_invalid",
    };
  }
  try {
    return {
      legacy: false,
      task_id: taskId,
      identity: normalizeExecutorIdentity(JSON.parse(identityJson)),
    };
  } catch (error) {
    return {
      legacy: false,
      task_id: taskId,
      identity: null,
      error: error.code || "executor_identity_invalid",
    };
  }
}

export function extractExecutorResultIdentity(text, taskId) {
  const blocks = text
    .split(/(?=^## Result)/m)
    .filter(
      (candidate) =>
        candidate.startsWith("## Result") &&
        candidate.match(/^- task_id：`([^`]+)`/m)?.[1] === taskId
    );
  const block =
    blocks.filter((candidate) => candidate.startsWith("## Result（inbox-daemon 回寫）")).at(-1) ??
    blocks.at(-1);
  if (!block) return { legacy: true, task_id: taskId, identity: null };
  const match = block.match(/- (?:executor_identity|identity)：\s*\n```json\s*\n([\s\S]*?)\n```/);
  if (!match) {
    const validation = block.match(/^- identity_validation：`([^`]+)`/m)?.[1];
    if (validation === "executor_identity_invalid") {
      return {
        legacy: false,
        task_id: taskId,
        identity: null,
        error: validation,
      };
    }
    return { legacy: true, task_id: taskId, identity: null };
  }
  try {
    return {
      legacy: false,
      task_id: taskId,
      identity: normalizeExecutorIdentity(JSON.parse(match[1])),
    };
  } catch (error) {
    return {
      legacy: false,
      task_id: taskId,
      identity: null,
      error: error.code || "executor_identity_invalid",
    };
  }
}

export function validateExecutorIdentityMatch(claimIdentity, resultIdentity) {
  if (!claimIdentity && !resultIdentity) {
    return { ok: true, code: "legacy", legacy: true, mismatches: [] };
  }
  if (!claimIdentity || !resultIdentity) {
    return {
      ok: false,
      code: "executor_identity_mismatch",
      legacy: false,
      mismatches: [claimIdentity ? "result_identity_missing" : "claim_identity_missing"],
    };
  }
  const claim = normalizeExecutorIdentity(claimIdentity);
  const result = normalizeExecutorIdentity(resultIdentity);
  const mismatches = EXECUTOR_IDENTITY_FIELDS.filter(
    (field) => JSON.stringify(claim[field]) !== JSON.stringify(result[field])
  );
  return {
    ok: mismatches.length === 0,
    code: mismatches.length === 0 ? "executor_identity_match" : "executor_identity_mismatch",
    legacy: false,
    mismatches,
  };
}

export function validateClaimResult(text, taskId, resultIdentity) {
  const claim = extractExecutorClaim(text);
  if (claim.legacy || !claim.identity || claim.task_id !== taskId) {
    return {
      ok: false,
      code: claim.error || "executor_identity_mismatch",
      legacy: claim.legacy,
      mismatches: claim.task_id !== taskId ? ["task_id"] : ["claim_identity_missing"],
    };
  }
  return validateExecutorIdentityMatch(claim.identity, resultIdentity);
}

export function validatePersistedClaimResult(text, taskId) {
  const claim = extractExecutorClaim(text);
  const result = extractExecutorResultIdentity(text, taskId);
  if (claim.error || result.error) {
    return {
      ok: false,
      code: claim.error || result.error,
      legacy: false,
      mismatches: [claim.error ? "claim_identity_invalid" : "result_identity_invalid"],
    };
  }
  if (claim.legacy && result.legacy) {
    return { ok: true, code: "legacy", legacy: true, mismatches: [] };
  }
  if (claim.task_id !== taskId || result.task_id !== taskId) {
    return {
      ok: false,
      code: "executor_identity_mismatch",
      legacy: false,
      mismatches: ["task_id"],
    };
  }
  return validateExecutorIdentityMatch(claim.identity, result.identity);
}

export function executorIdentityMarkdown(identity, validation) {
  return `- executor_identity：\n\`\`\`json\n${JSON.stringify(
    normalizeExecutorIdentity(identity),
    null,
    2
  )}\n\`\`\`\n- identity_validation：\`${validation.code}\``;
}

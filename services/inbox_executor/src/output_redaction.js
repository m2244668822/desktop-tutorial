export const REDACTION_MARKER = "[REDACTED_CREDENTIAL]";

const credentialPatterns = [
  /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b/g,
  /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/g,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
];

export function sanitizeSensitiveOutput(value) {
  let output = String(value ?? "");

  output = output.replace(
    /\b(authorization\s*:\s*)(?:(?:bearer|basic)\s+)?(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)/gi,
    `$1${REDACTION_MARKER}`,
  );

  output = output.replace(
    /\b((?:(?:OPENAI|CODEX)_API_KEY|GITHUB_TOKEN|GH_TOKEN)\s*[=:]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)/gi,
    `$1${REDACTION_MARKER}`,
  );

  for (const pattern of credentialPatterns) {
    output = output.replace(pattern, REDACTION_MARKER);
  }

  return output;
}

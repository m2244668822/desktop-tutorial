#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "repo_secret_hygiene_latest.json"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass(frozen=True)
class SecretPattern:
    id: str
    regex: re.Pattern[str]
    description: str


@dataclass
class Finding:
    file: str
    line: int
    pattern: str
    description: str
    redacted: str


SECRET_PATTERNS = [
    SecretPattern("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "OpenAI-style API key"),
    SecretPattern("github_pat", re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"), "GitHub personal access token"),
    SecretPattern("aws_access_key", re.compile(r"\bA[KS]IA[0-9A-Z]{16}\b"), "AWS access key"),
    SecretPattern("gemini_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "Google/Gemini API key"),
    SecretPattern("groq_api_key", re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"), "Groq API key"),
    SecretPattern("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9_-]{20,}\b"), "Hugging Face token"),
    SecretPattern("nvidia_api_key", re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}\b"), "NVIDIA API key"),
    SecretPattern(
        "private_key",
        re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----"),
        "Private key material",
    ),
]

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".mp3",
    ".wav",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".sqlite",
    ".db",
}

REQUIRED_GITIGNORE_PATTERNS = [
    ".env",
    ".env.*.local",
    "*.key",
    "*.pem",
    "data/",
    "logs/",
    "reports/*.json",
]


def run_git(args: list[str], root: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def tracked_files(root: Path = ROOT) -> list[str]:
    proc = run_git(["ls-files"], root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git ls-files failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def redacted_match(value: str) -> str:
    value = value.strip()
    if len(value) <= 10:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def should_skip_file(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTENSIONS


def scan_file(path: Path, rel_path: str, max_file_bytes: int) -> tuple[list[Finding], str]:
    if should_skip_file(path):
        return [], "binary_extension"
    try:
        if path.stat().st_size > max_file_bytes:
            return [], "too_large"
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [], "unreadable"

    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            match = pattern.regex.search(line)
            if not match:
                continue
            findings.append(
                Finding(
                    rel_path,
                    line_number,
                    pattern.id,
                    pattern.description,
                    redacted_match(match.group(0)),
                )
            )
            break
    return findings, "scanned"


def gitignore_state(root: Path = ROOT) -> dict[str, Any]:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    missing = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in text]
    return {
        "path": str(path),
        "exists": path.exists(),
        "required_patterns": REQUIRED_GITIGNORE_PATTERNS,
        "missing": missing,
        "ok": path.exists() and not missing,
    }


def build_payload(root: Path = ROOT, max_file_bytes: int = 1_000_000) -> dict[str, Any]:
    files = tracked_files(root)
    findings: list[Finding] = []
    skipped: dict[str, int] = {}
    scanned = 0
    for rel_path in files:
        path = root / rel_path
        if not path.exists() or not path.is_file():
            skipped["missing_or_not_file"] = skipped.get("missing_or_not_file", 0) + 1
            continue
        file_findings, state = scan_file(path, rel_path, max_file_bytes)
        if state == "scanned":
            scanned += 1
        else:
            skipped[state] = skipped.get(state, 0) + 1
        findings.extend(file_findings)

    ignore = gitignore_state(root)
    ok = not findings and bool(ignore.get("ok"))
    next_actions = []
    if findings:
        next_actions.append(
            {
                "source": "repo_secret_hygiene",
                "status": "possible_secret_found",
                "summary": "Remove possible secrets from tracked files and rotate any exposed keys.",
                "windows": ["git grep -n <redacted-pattern>", "git status -sb"],
                "macos": ["git grep -n <redacted-pattern>", "git status -sb"],
                "verify": "python tools/repo_secret_hygiene.py should report ready.",
                "evidence": {"finding_count": len(findings), "findings": [asdict(item) for item in findings[:20]]},
            }
        )
    if not ignore.get("ok"):
        next_actions.append(
            {
                "source": "repo_secret_hygiene",
                "status": "missing_gitignore_patterns",
                "summary": "Add missing runtime and secret patterns to .gitignore.",
                "windows": ["notepad .gitignore"],
                "macos": ["${EDITOR:-vi} .gitignore"],
                "verify": "repo_secret_hygiene gitignore.missing should be empty.",
                "evidence": {"missing": ignore.get("missing", [])},
            }
        )

    return {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(root),
        "ok": ok,
        "status": "ready" if ok else "attention_required",
        "tracked_file_count": len(files),
        "scanned_file_count": scanned,
        "skipped": skipped,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings[:100]],
        "gitignore": ignore,
        "next_actions": next_actions,
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked repo files for obvious leaked secrets.")
    parser.add_argument("--json-out", default=str(DEFAULT_REPORT))
    parser.add_argument("--max-file-bytes", type=int, default=1_000_000)
    args = parser.parse_args()

    payload = build_payload(ROOT, args.max_file_bytes)
    write_report(payload, Path(args.json_out))

    print("== Repo Secret Hygiene ==")
    print(f"status: {payload['status']}")
    print(f"tracked: {payload['tracked_file_count']} scanned: {payload['scanned_file_count']}")
    print(f"findings: {payload['finding_count']}")
    if payload["findings"]:
        for item in payload["findings"][:10]:
            print(f"- {item['file']}:{item['line']} {item['pattern']} {item['redacted']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

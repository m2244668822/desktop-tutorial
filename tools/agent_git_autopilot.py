#!/usr/bin/env python3
"""
Agent Git Autopilot

Purpose:
- Classify changed files into domains (frontend/backend/db/docs/mixed)
- Recommend branch prefix and validation profile
- Optionally enforce pre-push guardrails

Usage:
  python3 tools/agent_git_autopilot.py plan
  python3 tools/agent_git_autopilot.py guard --strict
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


DOMAIN_RULES = {
    "frontend": (
        "templates/",
        "static/",
        "cursor-agent-sidebar-extension/",
    ),
    "backend": (
        "chatgpt_server.py",
        "desktop_chat_app.py",
        "agents.py",
        "tools/",
        "tests/",
    ),
    "db": (
        "instance/",
        "tools/migrate_sqlite_to_postgres.py",
        "docs/dev/DB_MIGRATION_RUNBOOK.md",
    ),
    "docs": (
        "docs/",
        "README",
    ),
}

SKILL_HINTS = {
    "frontend": ["frontend-skill", "systematic-debugging"],
    "backend": ["systematic-debugging", "open-source-maintainer"],
    "db": ["systematic-debugging"],
    "docs": ["internal-comms"],
    "mixed": ["systematic-debugging", "open-source-maintainer", "internal-comms"],
}

BRANCH_HINTS = {
    "frontend": "codex/frontend-",
    "backend": "codex/backend-",
    "db": "codex/db-",
    "docs": "codex/docs-",
    "mixed": "codex/integration-",
}


@dataclass
class AutopilotPlan:
    changed_files: list[str]
    domains: list[str]
    dominant_domain: str
    branch_prefix: str
    skills: list[str]
    checks: list[str]


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _collect_changed_files(cwd: Path) -> list[str]:
    # staged + unstaged + untracked
    staged = _run_git(["diff", "--cached", "--name-only"], cwd)
    unstaged = _run_git(["diff", "--name-only"], cwd)
    untracked = _run_git(["ls-files", "--others", "--exclude-standard"], cwd)
    files = set()
    for proc in (staged, unstaged, untracked):
        for line in proc.stdout.splitlines():
            path = line.strip()
            if path:
                files.add(path)
    return sorted(files)


def _path_matches(path: str, marker: str) -> bool:
    if marker.endswith("/"):
        return path.startswith(marker)
    return path == marker or path.startswith(marker + "/")


def _classify_domains(changed_files: list[str]) -> list[str]:
    if not changed_files:
        return []
    hit = set()
    for file_path in changed_files:
        for domain, markers in DOMAIN_RULES.items():
            if any(_path_matches(file_path, marker) for marker in markers):
                hit.add(domain)
    if not hit:
        hit.add("backend")
    return sorted(hit)


def _dominant_domain(domains: list[str]) -> str:
    if not domains:
        return "docs"
    if len(domains) == 1:
        return domains[0]
    if "backend" in domains and "db" in domains:
        return "mixed"
    if "frontend" in domains and "backend" in domains:
        return "mixed"
    return "mixed"


def _checks_for_domain(domain: str) -> list[str]:
    base = ["python3 -m py_compile tools/agent_git_autopilot.py"]
    if domain in {"backend", "db", "mixed"}:
        base.append("tools/run_full_verification.sh")
    if domain in {"frontend", "mixed"}:
        base.append("python3 -m py_compile chatgpt_server.py")
    if domain == "db":
        base.append("python3 tools/migrate_sqlite_to_postgres.py --help")
    return base


def build_plan(cwd: Path) -> AutopilotPlan:
    changed_files = _collect_changed_files(cwd)
    domains = _classify_domains(changed_files)
    dominant = _dominant_domain(domains)
    return AutopilotPlan(
        changed_files=changed_files,
        domains=domains,
        dominant_domain=dominant,
        branch_prefix=BRANCH_HINTS.get(dominant, "codex/integration-"),
        skills=SKILL_HINTS.get(dominant, SKILL_HINTS["mixed"]),
        checks=_checks_for_domain(dominant),
    )


def cmd_plan(cwd: Path) -> int:
    plan = build_plan(cwd)
    payload = asdict(plan)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_guard(cwd: Path, strict: bool) -> int:
    plan = build_plan(cwd)
    print(
        f"[autopilot] dominant_domain={plan.dominant_domain} "
        f"branch_prefix={plan.branch_prefix} skills={','.join(plan.skills)}"
    )
    if not plan.changed_files:
        print("[autopilot] no local changes detected")
        return 0

    # Block runtime data tracking in push path
    blocked_prefixes = ("instance/", "logs/", "tmp/", "uploads/", "archives/", "backups/")
    blocked_files = [path for path in plan.changed_files if path.startswith(blocked_prefixes)]
    if blocked_files:
        print("[autopilot] blocked: runtime/generated files detected:")
        for path in blocked_files:
            print(f"  - {path}")
        return 1

    if strict:
        for cmd in plan.checks:
            print(f"[autopilot] run: {cmd}")
            proc = subprocess.run(cmd, cwd=str(cwd), shell=True, check=False)
            if proc.returncode != 0:
                print(f"[autopilot] check failed: {cmd}")
                return proc.returncode

    return 0


def _safe_slug(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in raw.strip().lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:48] if cleaned else ""


def _current_branch(cwd: Path) -> str:
    proc = _run_git(["branch", "--show-current"], cwd)
    return proc.stdout.strip()


def cmd_checkout(cwd: Path, suffix: str) -> int:
    plan = build_plan(cwd)
    branch_prefix = plan.branch_prefix
    dynamic_suffix = _safe_slug(suffix)
    if not dynamic_suffix:
        dynamic_suffix = datetime.now().strftime("%Y%m%d-%H%M")
    branch_name = f"{branch_prefix}{dynamic_suffix}"

    current = _current_branch(cwd)
    if current == branch_name:
        print(f"[autopilot] already on branch: {branch_name}")
        return 0

    proc = _run_git(["checkout", "-B", branch_name], cwd)
    if proc.returncode != 0:
        print(proc.stderr.strip() or proc.stdout.strip())
        return proc.returncode

    print(
        json.dumps(
            {
                "branch": branch_name,
                "dominant_domain": plan.dominant_domain,
                "skills": plan.skills,
                "checks": plan.checks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Git Autopilot")
    parser.add_argument("command", choices=["plan", "guard", "checkout"])
    parser.add_argument("--strict", action="store_true", help="run suggested checks and fail on error")
    parser.add_argument("--cwd", default=".", help="project root")
    parser.add_argument("--suffix", default="", help="branch suffix for checkout mode")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    if args.command == "plan":
        return cmd_plan(cwd)
    if args.command == "checkout":
        return cmd_checkout(cwd, suffix=args.suffix)
    return cmd_guard(cwd, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())

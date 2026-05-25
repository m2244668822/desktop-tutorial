#!/usr/bin/env python3
"""
One-shot verification for:
1) Private showcase repository security posture
2) SQLite -> PostgreSQL migration validation

Example:
  python3 tools/verify_repo_and_db.py \
    --repo m2244668822/desktop-tutorial \
    --base-url http://127.0.0.1:5001 \
    --sqlite-path instance/chat_history.db \
    --postgres-url "$APP_DATABASE_URL" \
    --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import sqlalchemy as sa


REQUIRED_BRANCHES = [
    "main",
    "codex/backend-mainline",
    "codex/frontend-showcase",
    "codex/db-migration-postgres",
]

REQUIRED_GITIGNORE_PATTERNS = [
    ".env",
    "instance/",
    "logs/",
    "tmp/",
    "uploads/",
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"op_[a-z0-9]{16,}"),
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
    ".aiff",
    ".zip",
    ".gz",
    ".tar",
}

SCAN_SKIP_FILES = {
    ".githooks/pre-commit",
    "tools/verify_repo_and_db.py",
}


@dataclass
class CheckItem:
    key: str
    ok: bool
    severity: str
    detail: str
    meta: dict[str, Any] | None = None


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def repo_slug_parts(repo_slug: str) -> tuple[str, str]:
    if "/" not in repo_slug:
        raise ValueError(f"Invalid repo slug: {repo_slug}")
    owner, repo = repo_slug.split("/", 1)
    return owner.strip(), repo.strip()


def github_get(path: str, token: str, timeout: int) -> requests.Response:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return requests.get(f"https://api.github.com{path}", headers=headers, timeout=timeout)


def check_local_repo(project_root: Path) -> list[CheckItem]:
    results: list[CheckItem] = []
    git_dir = project_root / ".git"
    results.append(
        CheckItem(
            key="local.git_initialized",
            ok=git_dir.exists(),
            severity="error",
            detail=".git exists" if git_dir.exists() else ".git not found",
        )
    )
    if not git_dir.exists():
        return results

    branch_proc = run_cmd(["git", "branch", "--format=%(refname:short)"], project_root)
    branches = set(line.strip() for line in branch_proc.stdout.splitlines() if line.strip())
    missing_branches = [branch for branch in REQUIRED_BRANCHES if branch not in branches]
    results.append(
        CheckItem(
            key="local.required_branches",
            ok=not missing_branches,
            severity="error",
            detail="all required branches exist"
            if not missing_branches
            else f"missing branches: {', '.join(missing_branches)}",
            meta={"branches": sorted(branches)},
        )
    )

    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        gitignore_text = gitignore_path.read_text(encoding="utf-8", errors="ignore")
    else:
        gitignore_text = ""
    missing_ignores = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in gitignore_text]
    results.append(
        CheckItem(
            key="local.gitignore_runtime_and_secret_patterns",
            ok=not missing_ignores,
            severity="error",
            detail="required ignore patterns found"
            if not missing_ignores
            else f"missing patterns: {', '.join(missing_ignores)}",
        )
    )

    tracked_proc = run_cmd(["git", "ls-files"], project_root)
    tracked_files = [line.strip() for line in tracked_proc.stdout.splitlines() if line.strip()]
    forbidden_prefixes = ("instance/", "logs/", "tmp/", "uploads/", "archives/", "backups/")
    forbidden_tracked = [
        path for path in tracked_files if any(path == prefix[:-1] or path.startswith(prefix) for prefix in forbidden_prefixes)
    ]
    results.append(
        CheckItem(
            key="local.no_runtime_data_tracked",
            ok=not forbidden_tracked,
            severity="error",
            detail="runtime data folders are not tracked"
            if not forbidden_tracked
            else f"tracked runtime paths: {', '.join(forbidden_tracked[:10])}",
            meta={"count": len(forbidden_tracked)},
        )
    )

    secret_hits: list[dict[str, Any]] = []
    for rel_path in tracked_files:
        if rel_path in SCAN_SKIP_FILES:
            continue
        path = project_root / rel_path
        if not path.exists() or not path.is_file():
            continue
        if path.suffix.lower() in BINARY_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                secret_hits.append(
                    {
                        "file": rel_path,
                        "pattern": pattern.pattern,
                        "snippet": match.group(0)[:24] + "...",
                    }
                )
                break

    results.append(
        CheckItem(
            key="local.secret_scan_tracked_files",
            ok=not secret_hits,
            severity="error",
            detail="no obvious secrets detected in tracked files"
            if not secret_hits
            else f"possible secrets found in {len(secret_hits)} files",
            meta={"hits": secret_hits[:20]},
        )
    )

    return results


def check_github_repo(repo_slug: str, token: str, timeout: int) -> list[CheckItem]:
    results: list[CheckItem] = []
    owner, repo = repo_slug_parts(repo_slug)

    repo_resp = github_get(f"/repos/{owner}/{repo}", token, timeout)
    if repo_resp.status_code != 200:
        results.append(
            CheckItem(
                key="github.repo_accessible",
                ok=False,
                severity="error",
                detail=f"cannot access repo: HTTP {repo_resp.status_code}",
                meta={"response": repo_resp.text[:500]},
            )
        )
        return results

    repo_data = repo_resp.json()
    results.append(
        CheckItem(
            key="github.repo_private",
            ok=bool(repo_data.get("private")),
            severity="error",
            detail="repository is private" if repo_data.get("private") else "repository is not private",
        )
    )

    collab_resp = github_get(f"/repos/{owner}/{repo}/collaborators?affiliation=direct&per_page=100", token, timeout)
    if collab_resp.status_code == 200:
        collaborators = collab_resp.json()
        outsider_collabs = [item.get("login") for item in collaborators if item.get("login") != owner]
        results.append(
            CheckItem(
                key="github.direct_collaborators_owner_only",
                ok=not outsider_collabs,
                severity="error",
                detail="no extra direct collaborators" if not outsider_collabs else f"extra direct collaborators: {', '.join(outsider_collabs)}",
                meta={"direct_collaborator_count": len(collaborators), "direct_collaborators": [item.get("login") for item in collaborators]},
            )
        )
    else:
        results.append(
            CheckItem(
                key="github.direct_collaborators_owner_only",
                ok=False,
                severity="warning",
                detail=f"cannot read collaborators: HTTP {collab_resp.status_code}",
                meta={"response": collab_resp.text[:500]},
            )
        )

    actions_resp = github_get(f"/repos/{owner}/{repo}/actions/permissions", token, timeout)
    if actions_resp.status_code == 200:
        actions = actions_resp.json()
        allowed_actions = str(actions.get("allowed_actions", "")).strip().lower()
        sha_pin = bool(actions.get("sha_pinning_required", False))
        allowed_ok = allowed_actions in {"local_only", "selected"}
        results.append(
            CheckItem(
                key="github.actions_policy_restricted",
                ok=allowed_ok,
                severity="warning",
                detail=f"allowed_actions={allowed_actions or 'unknown'}",
                meta=actions,
            )
        )
        results.append(
            CheckItem(
                key="github.actions_sha_pinning_required",
                ok=sha_pin,
                severity="warning",
                detail=f"sha_pinning_required={sha_pin}",
                meta=actions,
            )
        )
    else:
        results.append(
            CheckItem(
                key="github.actions_policy_restricted",
                ok=False,
                severity="warning",
                detail=f"cannot read actions permissions: HTTP {actions_resp.status_code}",
                meta={"response": actions_resp.text[:500]},
            )
        )

    return results


def _normalize_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _table_counts(engine: sa.Engine, table_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table_name in table_names:
            stmt = sa.text(f'SELECT COUNT(*) AS count_value FROM "{table_name}"')
            counts[table_name] = int(conn.execute(stmt).scalar_one() or 0)
    return counts


def _sample_hashes(engine: sa.Engine, table_name: str, sample_size: int) -> list[str]:
    inspector = sa.inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    pk = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    order_cols = pk if pk else columns[:1]
    if not columns or not order_cols:
        return []

    quoted_cols = ", ".join(f'"{col}"' for col in columns)
    order_expr = ", ".join(f'"{col}"' for col in order_cols)
    stmt = sa.text(f'SELECT {quoted_cols} FROM "{table_name}" ORDER BY {order_expr} LIMIT :limit_value')

    hashes: list[str] = []
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"limit_value": sample_size}).mappings().all()
    for row in rows:
        normalized = json.dumps({k: row.get(k) for k in columns}, ensure_ascii=False, default=str, sort_keys=True)
        hashes.append(hashlib.sha256(normalized.encode("utf-8")).hexdigest())
    return hashes


def check_db_migration(
    sqlite_path: Path,
    postgres_url: str,
    core_tables: list[str],
    sample_size: int,
) -> list[CheckItem]:
    results: list[CheckItem] = []
    if not sqlite_path.exists():
        results.append(
            CheckItem(
                key="db.sqlite_source_exists",
                ok=False,
                severity="error",
                detail=f"sqlite source not found: {sqlite_path}",
            )
        )
        return results

    pg_url = _normalize_url(postgres_url)
    if not pg_url:
        results.append(
            CheckItem(
                key="db.postgres_url_present",
                ok=False,
                severity="error",
                detail="postgres url missing",
            )
        )
        return results

    sqlite_engine = sa.create_engine(f"sqlite:///{sqlite_path}")
    pg_engine = sa.create_engine(pg_url, pool_pre_ping=True)

    sqlite_inspector = sa.inspect(sqlite_engine)
    pg_inspector = sa.inspect(pg_engine)
    sqlite_tables = set(sqlite_inspector.get_table_names())
    pg_tables = set(pg_inspector.get_table_names())

    missing_in_pg = [name for name in core_tables if name in sqlite_tables and name not in pg_tables]
    results.append(
        CheckItem(
            key="db.core_tables_exist_in_postgres",
            ok=not missing_in_pg,
            severity="error",
            detail="all core sqlite tables exist in postgres"
            if not missing_in_pg
            else f"missing in postgres: {', '.join(missing_in_pg)}",
        )
    )

    comparable_tables = [name for name in core_tables if name in sqlite_tables and name in pg_tables]
    if not comparable_tables:
        results.append(
            CheckItem(
                key="db.comparable_tables_present",
                ok=False,
                severity="error",
                detail="no comparable core tables found",
            )
        )
        return results

    sqlite_counts = _table_counts(sqlite_engine, comparable_tables)
    pg_counts = _table_counts(pg_engine, comparable_tables)
    count_mismatch = {
        name: {"sqlite": sqlite_counts[name], "postgres": pg_counts[name]}
        for name in comparable_tables
        if sqlite_counts[name] != pg_counts[name]
    }
    results.append(
        CheckItem(
            key="db.core_table_row_counts_match",
            ok=not count_mismatch,
            severity="error",
            detail="row counts match on all comparable core tables"
            if not count_mismatch
            else f"row count mismatch tables: {', '.join(count_mismatch.keys())}",
            meta={"sqlite_counts": sqlite_counts, "postgres_counts": pg_counts, "mismatch": count_mismatch},
        )
    )

    sample_mismatch: dict[str, Any] = {}
    for table_name in comparable_tables:
        sqlite_hashes = _sample_hashes(sqlite_engine, table_name, sample_size)
        pg_hashes = _sample_hashes(pg_engine, table_name, sample_size)
        if sqlite_hashes != pg_hashes:
            sample_mismatch[table_name] = {
                "sqlite_sample_count": len(sqlite_hashes),
                "postgres_sample_count": len(pg_hashes),
            }

    results.append(
        CheckItem(
            key="db.sample_hash_match",
            ok=not sample_mismatch,
            severity="warning",
            detail="sample hashes match on comparable core tables"
            if not sample_mismatch
            else f"sample mismatch tables: {', '.join(sample_mismatch.keys())}",
            meta={"sample_size": sample_size, "mismatch": sample_mismatch},
        )
    )

    return results


def check_service_health(base_url: str, timeout: int) -> list[CheckItem]:
    results: list[CheckItem] = []
    base = base_url.rstrip("/")
    for endpoint in ("/health", "/status"):
        url = f"{base}{endpoint}"
        try:
            response = requests.get(url, timeout=timeout)
            ok = response.status_code < 400
            detail = f"{url} -> HTTP {response.status_code}"
            meta: dict[str, Any] = {}
            if endpoint == "/health":
                try:
                    payload = response.json()
                    meta["status"] = payload.get("status")
                    meta["database"] = payload.get("database")
                except Exception:
                    pass
            results.append(
                CheckItem(
                    key=f"service{endpoint.replace('/', '.')}",
                    ok=ok,
                    severity="warning",
                    detail=detail,
                    meta=meta or None,
                )
            )
        except Exception as exc:
            results.append(
                CheckItem(
                    key=f"service{endpoint.replace('/', '.')}",
                    ok=False,
                    severity="warning",
                    detail=f"{url} -> request failed: {exc}",
                )
            )
    return results


def summarize(results: list[CheckItem]) -> dict[str, int]:
    summary = {"total": len(results), "ok": 0, "failed": 0, "warnings": 0, "errors": 0}
    for item in results:
        if item.ok:
            summary["ok"] += 1
        else:
            summary["failed"] += 1
            if item.severity == "warning":
                summary["warnings"] += 1
            else:
                summary["errors"] += 1
    return summary


def print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("=== Verification Summary ===")
    print(
        f"total={summary['total']} ok={summary['ok']} "
        f"failed={summary['failed']} warnings={summary['warnings']} errors={summary['errors']}"
    )
    for item in report["checks"]:
        symbol = "PASS" if item["ok"] else "FAIL"
        print(f"[{symbol}] {item['key']}: {item['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify repo security posture and DB migration quality.")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--repo", default="", help="GitHub repo slug, e.g. owner/repo")
    parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--sqlite-path", default="instance/chat_history.db")
    parser.add_argument("--postgres-url", default=os.getenv("APP_DATABASE_URL", ""))
    parser.add_argument("--core-tables", default="chat_history,agent_task,xiaobian_profile,dispatcher_rule,agent_signal")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--http-timeout", type=int, default=10)
    parser.add_argument("--skip-local-checks", action="store_true")
    parser.add_argument("--skip-service-checks", action="store_true")
    parser.add_argument("--skip-github-checks", action="store_true")
    parser.add_argument("--skip-db-checks", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any warning/error check fails")
    parser.add_argument(
        "--report-file",
        default="logs/verification_reports/latest_verification_report.json",
        help="Path to write JSON report",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    sqlite_path = Path(args.sqlite_path).expanduser()
    if not sqlite_path.is_absolute():
        sqlite_path = project_root / sqlite_path
    sqlite_path = sqlite_path.resolve()

    checks: list[CheckItem] = []
    if not args.skip_local_checks:
        checks.extend(check_local_repo(project_root))
    if not args.skip_service_checks:
        checks.extend(check_service_health(args.base_url, args.http_timeout))

    if not args.skip_github_checks and args.repo:
        if args.github_token:
            checks.extend(check_github_repo(args.repo, args.github_token, args.http_timeout))
        else:
            checks.append(
                CheckItem(
                    key="github.token_present",
                    ok=False,
                    severity="warning",
                    detail="GitHub token missing; skipped GitHub policy checks",
                )
            )

    if not args.skip_db_checks and args.postgres_url:
        core_tables = [item.strip() for item in args.core_tables.split(",") if item.strip()]
        checks.extend(
            check_db_migration(
                sqlite_path=sqlite_path,
                postgres_url=args.postgres_url,
                core_tables=core_tables,
                sample_size=max(1, args.sample_size),
            )
        )
    elif not args.skip_db_checks:
        checks.append(
            CheckItem(
                key="db.postgres_url_present",
                ok=False,
                severity="warning",
                detail="APP_DATABASE_URL/--postgres-url missing; skipped db migration checks",
            )
        )

    summary = summarize(checks)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "repo": args.repo,
        "base_url": args.base_url,
        "summary": summary,
        "checks": [asdict(item) for item in checks],
    }

    report_path = Path(args.report_file).expanduser()
    if not report_path.is_absolute():
        report_path = project_root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(report)
    print(f"\nreport_file={report_path}")

    if args.strict and summary["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

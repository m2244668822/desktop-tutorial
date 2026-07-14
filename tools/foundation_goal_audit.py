#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEALTH_REPORT = ROOT / "reports" / "foundation_health_latest.json"
DEFAULT_REPORT = ROOT / "reports" / "foundation_goal_audit_latest.json"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class Requirement:
    id: str
    title: str
    status: str
    summary: str
    evidence: dict[str, Any]
    next_actions: list[dict[str, Any]]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def checks_by_name(health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    for item in health.get("checks") or []:
        if isinstance(item, dict) and item.get("name"):
            checks[str(item["name"])] = item
    return checks


def actions_for(health: dict[str, Any], sources: set[str]) -> list[dict[str, Any]]:
    return [
        item
        for item in health.get("next_actions") or []
        if isinstance(item, dict) and str(item.get("source")) in sources
    ]


def compact_check(check: dict[str, Any] | None) -> dict[str, Any]:
    if not check:
        return {"present": False}
    return {
        "present": True,
        "ok": bool(check.get("ok")),
        "status": check.get("status"),
    }


def _status_for_missing_or_failing(
    checks: dict[str, dict[str, Any]],
    required: list[str],
    *,
    accepted_status: dict[str, set[str]] | None = None,
) -> tuple[str, list[str], list[str]]:
    accepted_status = accepted_status or {}
    missing = [name for name in required if name not in checks]
    failing: list[str] = []
    for name in required:
        check = checks.get(name)
        if not check:
            continue
        status_ok = True
        if name in accepted_status:
            status_ok = str(check.get("status")) in accepted_status[name]
        if not bool(check.get("ok")) or not status_ok:
            failing.append(name)
    if missing:
        return "missing_evidence", missing, failing
    if failing:
        return "incomplete", missing, failing
    return "passed", missing, failing


def _requirement_from_checks(
    health: dict[str, Any],
    checks: dict[str, dict[str, Any]],
    *,
    req_id: str,
    title: str,
    required: list[str],
    summary_ok: str,
    summary_bad: str,
    accepted_status: dict[str, set[str]] | None = None,
) -> Requirement:
    status, missing, failing = _status_for_missing_or_failing(
        checks,
        required,
        accepted_status=accepted_status,
    )
    sources = set(required)
    return Requirement(
        req_id,
        title,
        status,
        summary_ok if status == "passed" else summary_bad,
        {
            "required_checks": required,
            "missing": missing,
            "failing": failing,
            "checks": {name: compact_check(checks.get(name)) for name in required},
        },
        actions_for(health, sources),
    )


def evaluate_architecture(health: dict[str, Any], checks: dict[str, dict[str, Any]]) -> Requirement:
    required = [
        "workspace_context",
        "runtime_dependencies",
        "runtime_service_controller",
        "ports",
        "gateway",
        "n8n",
        "knowledge_hub",
        "py_compile",
    ]
    return _requirement_from_checks(
        health,
        checks,
        req_id="foundation_architecture_ready",
        title="Foundation Architecture Ready",
        required=required,
        summary_ok="Workspace, dependencies, controlled services, gateway, n8n visibility, data manifest, and Python compile gates are ready.",
        summary_bad="Foundation architecture still lacks complete health evidence or has failing core checks.",
    )


def evaluate_frontend(health: dict[str, Any], checks: dict[str, dict[str, Any]]) -> Requirement:
    required = ["frontend_static_contract", "browser_smoke"]
    status, missing, failing = _status_for_missing_or_failing(
        checks,
        required,
        accepted_status={"browser_smoke": {"ready"}, "frontend_static_contract": {"ready"}},
    )
    browser = checks.get("browser_smoke") or {}
    viewports = ((browser.get("detail") or {}).get("viewports") or [])
    ready_viewports = [
        item
        for item in viewports
        if isinstance(item, dict) and item.get("ok") and item.get("status") == "ready"
    ]
    matrix_ok = len(ready_viewports) >= 3
    if status == "passed" and not matrix_ok:
        status = "incomplete"
        failing = sorted(set([*failing, "browser_smoke_matrix"]))
    return Requirement(
        "frontend_issue_free",
        "Frontend Issue-Free Gate",
        status,
        (
            "Static chat shell contract and mobile/tablet/desktop browser smoke evidence are all ready."
            if status == "passed"
            else "Frontend cannot be called issue-free without static contract plus mobile/tablet/desktop browser smoke readiness."
        ),
        {
            "required_checks": required,
            "missing": missing,
            "failing": failing,
            "checks": {name: compact_check(checks.get(name)) for name in required},
            "browser_smoke_viewports": [
                {
                    "name": item.get("name"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "ok": item.get("ok"),
                    "status": item.get("status"),
                }
                for item in viewports
                if isinstance(item, dict)
            ],
        },
        actions_for(health, set(required)),
    )


def evaluate_backend_detection(health: dict[str, Any], checks: dict[str, dict[str, Any]]) -> Requirement:
    required = [
        "runtime_dependencies",
        "runtime_service_controller",
        "ports",
        "gateway",
        "openclaw_runtime",
        "n8n",
        "n8n_workflow_preflight",
        "knowledge_hub",
        "py_compile",
    ]
    return _requirement_from_checks(
        health,
        checks,
        req_id="backend_multi_angle_detection",
        title="Backend Multi-Angle Detection",
        required=required,
        summary_ok="Backend state is observable through dependency, controller, port, API, OpenClaw, n8n, data, and compile checks.",
        summary_bad="Backend diagnosis is missing one or more required evidence angles.",
        accepted_status={
            "n8n_workflow_preflight": {
                "ready_for_activation",
                "ready_for_manual_execution",
                "blocked_for_activation",
            },
        },
    )


def _dirty_only_reports(git_check: dict[str, Any] | None) -> bool:
    if not git_check:
        return False
    status_lines = (git_check.get("detail") or {}).get("status") or []
    dirty = [str(line) for line in status_lines if not str(line).startswith("##")]
    if not dirty:
        return True
    return all(" reports/" in f" {line.replace(chr(92), '/')}" for line in dirty)


def evaluate_optimization_flow(health: dict[str, Any], checks: dict[str, dict[str, Any]]) -> Requirement:
    required_docs = [
        ROOT / "docs" / "dev" / "FOUNDATION_OPTIMIZATION_FLOW_2026-06-28.md",
        ROOT / "docs" / "dev" / "MAC_GIT_HANDOFF_PACKAGE_2026-06-29.md",
    ]
    docs_present = {str(path.relative_to(ROOT)): path.exists() for path in required_docs}
    git_check = checks.get("git")
    git_ok = bool(git_check and git_check.get("ok"))
    reports_only_dirty = _dirty_only_reports(git_check)
    status = "passed" if all(docs_present.values()) and git_ok and reports_only_dirty else "incomplete"
    return Requirement(
        "optimization_flow_no_sprawl",
        "Optimization Flow Without Sprawl",
        status,
        (
            "Optimization flow and handoff docs exist, and Git scope is clean or limited to generated reports."
            if status == "passed"
            else "Optimization flow evidence is incomplete or Git has source changes that need review."
        ),
        {
            "docs_present": docs_present,
            "git": compact_check(git_check),
            "dirty_only_reports": reports_only_dirty,
        },
        actions_for(health, {"git"}),
    )


def evaluate_secret_hygiene(health: dict[str, Any], checks: dict[str, dict[str, Any]]) -> Requirement:
    check = checks.get("repo_secret_hygiene")
    detail = (check or {}).get("detail") or {}
    report = detail.get("report") or {}
    passed = bool(
        check
        and check.get("ok")
        and check.get("status") == "ready"
        and report.get("finding_count", 0) == 0
        and (report.get("gitignore") or {}).get("ok")
    )
    return Requirement(
        "repo_secret_hygiene_ready",
        "Repo Secret Hygiene Ready",
        "passed" if passed else ("missing_evidence" if not check else "incomplete"),
        (
            "Tracked files have no obvious API keys and .gitignore protects runtime/secret artifacts."
            if passed
            else "Repo secret hygiene is not fully proven; do not solve n8n credentials by committing secrets."
        ),
        {
            "check": compact_check(check),
            "finding_count": report.get("finding_count"),
            "gitignore": report.get("gitignore", {}),
            "report_path": detail.get("report_path"),
        },
        actions_for(health, {"repo_secret_hygiene"}),
    )


def evaluate_openclaw(checks: dict[str, dict[str, Any]], health: dict[str, Any]) -> Requirement:
    check = checks.get("openclaw_runtime")
    detail = (check or {}).get("detail") or {}
    local_execution = detail.get("local_execution") or {}
    criteria = local_execution.get("criteria") or {}
    supported = bool(local_execution.get("supported"))
    criteria_ok = bool(criteria) and all(bool(value) for value in criteria.values())
    passed = bool(check and check.get("ok") and check.get("status") == "ready" and supported and criteria_ok)
    return Requirement(
        "openclaw_local_execution_ready",
        "OpenClaw Local Execution Ready",
        "passed" if passed else "incomplete",
        (
            "OpenClaw is installed and local execution is proven by gateway listener and health criteria."
            if passed
            else "OpenClaw local execution is not fully proven by the current health report."
        ),
        {
            "check": compact_check(check),
            "health": detail.get("health"),
            "local_execution": local_execution,
            "gateway": detail.get("gateway", {}),
            "governance": detail.get("governance", {}),
        },
        actions_for(health, {"openclaw_runtime"}),
    )


def evaluate_n8n_activation(checks: dict[str, dict[str, Any]], health: dict[str, Any]) -> Requirement:
    check = checks.get("n8n_workflow_preflight")
    report = ((check or {}).get("detail") or {}).get("report") or {}
    credential_plan = report.get("credential_setup_plan") or {}
    manual_plan = report.get("manual_execution_plan") or {}
    ready = (
        bool(check and check.get("ok"))
        and str(report.get("status")) == "ready_for_activation"
        and bool(report.get("ok_for_activation"))
        and str(credential_plan.get("status") or "ready") == "ready"
        and str(manual_plan.get("status") or "ready") == "ready"
    )
    if ready:
        status = "passed"
        summary = "n8n workflow preflight is ready for activation with credentials bound."
    elif not check:
        status = "missing_evidence"
        summary = "n8n activation readiness has no preflight evidence."
    elif str(report.get("status")) == "blocked_for_activation":
        status = "blocked"
        summary = "n8n activation is blocked by preflight, currently by real provider credential work."
    elif str(report.get("status")) == "ready_for_manual_execution":
        status = "incomplete"
        summary = "n8n credentials are ready enough to run a controlled manual execution, but activation is not proven yet."
    else:
        status = "incomplete"
        summary = "n8n activation readiness is incomplete or preflight did not produce a ready report."
    return Requirement(
        "n8n_activation_ready",
        "n8n Activation Ready",
        status,
        summary,
        {
            "check": compact_check(check),
            "preflight_status": report.get("status"),
            "ok_for_activation": report.get("ok_for_activation"),
            "blocker_count": report.get("blocker_count"),
            "credential_setup_plan": credential_plan,
            "manual_execution_plan": manual_plan,
            "issues": report.get("issues", [])[:8],
        },
        actions_for(health, {"n8n_workflow_preflight"}),
    )


def build_audit(health: dict[str, Any], health_report_path: Path) -> dict[str, Any]:
    checks = checks_by_name(health)
    requirements = [
        evaluate_architecture(health, checks),
        evaluate_frontend(health, checks),
        evaluate_backend_detection(health, checks),
        evaluate_optimization_flow(health, checks),
        evaluate_secret_hygiene(health, checks),
        evaluate_openclaw(checks, health),
        evaluate_n8n_activation(checks, health),
    ]
    incomplete = [item for item in requirements if item.status != "passed"]
    return {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(ROOT),
        "health_report": str(health_report_path),
        "ok": not incomplete,
        "status": "complete" if not incomplete else "incomplete",
        "completion_claim_allowed": not incomplete,
        "requirement_count": len(requirements),
        "passed_count": len(requirements) - len(incomplete),
        "incomplete_count": len(incomplete),
        "requirements": [asdict(item) for item in requirements],
    }


def run_health_report(path: Path, browser_smoke: str) -> None:
    cmd = [
        sys.executable,
        "tools/foundation_health_check.py",
        "--browser-smoke",
        browser_smoke,
        "--json-out",
        str(path),
    ]
    subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit foundation readiness against the active goal.")
    parser.add_argument("--health-report", default=str(DEFAULT_HEALTH_REPORT))
    parser.add_argument("--json-out", default=str(DEFAULT_REPORT))
    parser.add_argument("--run-health", action="store_true")
    parser.add_argument(
        "--browser-smoke",
        choices=("auto", "required", "off"),
        default="required",
        help="Browser smoke mode when --run-health is used.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Return 0 even when the goal audit is incomplete.",
    )
    args = parser.parse_args()

    health_report = Path(args.health_report)
    if args.run_health:
        run_health_report(health_report, args.browser_smoke)
    health = load_json(health_report)
    payload = build_audit(health, health_report)
    write_report(payload, Path(args.json_out))

    print("== Foundation Goal Audit ==")
    print(f"status: {payload['status']}")
    print(f"passed: {payload['passed_count']}/{payload['requirement_count']}")
    for item in payload["requirements"]:
        print(f"[{item['status']}] {item['id']}: {item['summary']}")

    if payload["ok"]:
        return 0
    return 0 if args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())

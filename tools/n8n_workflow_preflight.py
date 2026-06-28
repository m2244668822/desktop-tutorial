#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "docs" / "superpowers" / "specs" / "n8n-workflow-xiaobian-video.json"
DEFAULT_DB = Path.home() / ".n8n" / "database.sqlite"
DEFAULT_REPORT = ROOT / "reports" / "n8n_workflow_preflight_latest.json"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    evidence: dict[str, Any]


def load_workflow(path: Path) -> tuple[dict[str, Any] | None, list[Issue]]:
    if not path.exists():
        return None, [
            Issue(
                "blocker",
                "missing_workflow_spec",
                "n8n workflow spec file is missing.",
                {"path": str(path)},
            )
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, [
            Issue(
                "blocker",
                "invalid_workflow_json",
                "n8n workflow spec is not valid JSON.",
                {"path": str(path), "error": str(exc)},
            )
        ]
    if not isinstance(payload, dict):
        return None, [
            Issue(
                "blocker",
                "invalid_workflow_shape",
                "n8n workflow spec must be a JSON object.",
                {"path": str(path), "type": type(payload).__name__},
            )
        ]
    return payload, []


def db_snapshot(db_path: Path, workflow_id: str, workflow_name: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "ok": False,
        "counts": {},
        "workflow": {},
        "error": "",
    }
    if not db_path.exists():
        snapshot["error"] = "database_not_found"
        return snapshot
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        for table in ("workflow_entity", "credentials_entity", "execution_entity"):
            snapshot["counts"][table] = int(
                con.execute(f"select count(*) from {table}").fetchone()[0]
            )
        row = con.execute(
            "select id, name, active from workflow_entity where id = ? or name = ? limit 1",
            (workflow_id, workflow_name),
        ).fetchone()
        if row:
            snapshot["workflow"] = dict(row)
        con.close()
        snapshot["ok"] = True
    except Exception as exc:  # noqa: BLE001
        snapshot["error"] = str(exc)
    return snapshot


def _node_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("id") or "<unnamed>")


def audit_credentials(nodes: list[dict[str, Any]], db: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    external_types = {
        "n8n-nodes-base.googleGemini": "Google Gemini",
        "n8n-nodes-base.openAi": "OpenAI",
    }
    for node in nodes:
        node_type = str(node.get("type") or "")
        provider = external_types.get(node_type)
        if not provider:
            continue
        if not node.get("credentials"):
            issues.append(
                Issue(
                    "blocker",
                    "missing_node_credentials",
                    f"{_node_name(node)} has no credential binding.",
                    {"node": _node_name(node), "type": node_type, "provider": provider},
                )
            )
    credential_count = int((db.get("counts") or {}).get("credentials_entity", 0) or 0)
    if db.get("ok") and credential_count == 0:
        issues.append(
            Issue(
                "blocker",
                "n8n_database_has_no_credentials",
                "n8n database contains zero credentials, so provider nodes cannot run.",
                {"db_path": db.get("path"), "credentials_entity": credential_count},
            )
        )
    elif not db.get("ok"):
        issues.append(
            Issue(
                "warning",
                "n8n_database_unavailable",
                "n8n database could not be inspected.",
                {"db_path": db.get("path"), "error": db.get("error")},
            )
        )
    return issues


def audit_execute_commands(nodes: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    ffmpeg_found = shutil.which("ffmpeg")
    command_nodes = [
        node for node in nodes if str(node.get("type") or "") == "n8n-nodes-base.executeCommand"
    ]
    for node in command_nodes:
        params = node.get("parameters") or {}
        command = str(params.get("command") or "")
        evidence = {"node": _node_name(node), "command": command}
        if "..." in command:
            issues.append(
                Issue(
                    "blocker",
                    "placeholder_command",
                    "Execute Command node still contains placeholder command text.",
                    evidence,
                )
            )
        bare_outputs = [
            token
            for token in (" image.png", " audio.mp3", " output.mp4")
            if token in f" {command} "
        ]
        if bare_outputs:
            issues.append(
                Issue(
                    "blocker",
                    "unsafe_relative_media_paths",
                    "FFmpeg command uses bare relative media paths instead of a controlled output directory.",
                    {**evidence, "bare_paths": [item.strip() for item in bare_outputs]},
                )
            )
        if not ffmpeg_found:
            issues.append(
                Issue(
                    "blocker",
                    "ffmpeg_not_found",
                    "ffmpeg is not available on PATH for the Execute Command node.",
                    {"node": _node_name(node)},
                )
            )
    if not command_nodes:
        issues.append(
            Issue(
                "warning",
                "missing_execute_command_node",
                "Workflow has no Execute Command node; media assembly may be incomplete.",
                {},
            )
        )
    return issues


def audit_safety(workflow: dict[str, Any], db: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    settings = workflow.get("settings") or {}
    meta = workflow.get("meta") or {}
    workflow_active = bool(workflow.get("active"))
    db_workflow = db.get("workflow") or {}
    db_active = bool(db_workflow.get("active")) if db_workflow else False

    if workflow_active or db_active:
        issues.append(
            Issue(
                "blocker",
                "workflow_active_before_preflight_clearance",
                "Workflow is active before credentials, cost controls, and FFmpeg safety are cleared.",
                {"spec_active": workflow_active, "db_active": db_active},
            )
        )
    if not settings.get("executionTimeout"):
        issues.append(
            Issue(
                "blocker",
                "missing_execution_timeout",
                "Workflow has no execution timeout cost/safety limit.",
                {"settings": settings},
            )
        )
    if not meta.get("cost_controls"):
        issues.append(
            Issue(
                "blocker",
                "missing_cost_controls",
                "Workflow meta has no explicit cost_controls block for paid provider nodes.",
                {"meta_keys": sorted(meta.keys())},
            )
        )
    if not settings.get("errorWorkflow") and not meta.get("error_policy"):
        issues.append(
            Issue(
                "blocker",
                "missing_error_handling_policy",
                "Workflow has no error workflow or meta.error_policy.",
                {"settings": settings, "meta_keys": sorted(meta.keys())},
            )
        )
    return issues


def audit_webhooks(nodes: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    for node in nodes:
        if str(node.get("type") or "") != "n8n-nodes-base.webhook":
            continue
        params = node.get("parameters") or {}
        if not params.get("path"):
            issues.append(
                Issue(
                    "blocker",
                    "webhook_missing_path",
                    "Webhook node has no path.",
                    {"node": _node_name(node)},
                )
            )
        if not params.get("authentication"):
            issues.append(
                Issue(
                    "blocker",
                    "webhook_without_auth",
                    "Webhook node has no authentication setting.",
                    {"node": _node_name(node), "path": params.get("path")},
                )
            )
    return issues


def run_preflight(spec_path: Path, db_path: Path) -> dict[str, Any]:
    workflow, issues = load_workflow(spec_path)
    if workflow is None:
        blockers = [issue for issue in issues if issue.severity == "blocker"]
        return {
            "ok_for_activation": False,
            "status": "invalid",
            "spec_path": str(spec_path),
            "db": {"path": str(db_path), "exists": db_path.exists()},
            "issues": [asdict(issue) for issue in issues],
            "blocker_count": len(blockers),
            "warning_count": len([issue for issue in issues if issue.severity == "warning"]),
        }

    nodes = workflow.get("nodes") or []
    if not isinstance(nodes, list):
        nodes = []
        issues.append(
            Issue(
                "blocker",
                "invalid_nodes_shape",
                "Workflow nodes must be a list.",
                {"nodes_type": type(workflow.get("nodes")).__name__},
            )
        )

    db = db_snapshot(
        db_path,
        str(workflow.get("id") or ""),
        str(workflow.get("name") or ""),
    )
    issues.extend(audit_credentials(nodes, db))
    issues.extend(audit_execute_commands(nodes))
    issues.extend(audit_webhooks(nodes))
    issues.extend(audit_safety(workflow, db))

    blockers = [issue for issue in issues if issue.severity == "blocker"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return {
        "ok_for_activation": not blockers,
        "status": "ready_for_activation" if not blockers else "blocked_for_activation",
        "spec_path": str(spec_path),
        "workflow": {
            "id": workflow.get("id", ""),
            "name": workflow.get("name", ""),
            "active": bool(workflow.get("active")),
            "node_count": len(nodes),
        },
        "db": db,
        "issues": [asdict(issue) for issue in issues],
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight n8n workflow before activation.")
    parser.add_argument("--workflow-spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--json-out", default=str(DEFAULT_REPORT))
    parser.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Return 0 even when activation blockers are found; useful for inventory health checks.",
    )
    args = parser.parse_args()

    payload = run_preflight(Path(args.workflow_spec), Path(args.db))
    write_report(payload, Path(args.json_out))

    print("== n8n Workflow Preflight ==")
    print(f"workflow: {payload.get('workflow', {}).get('name', args.workflow_spec)}")
    print(f"status: {payload['status']}")
    print(f"blockers: {payload['blocker_count']} warnings: {payload['warning_count']}")
    for issue in payload["issues"][:10]:
        print(f"[{issue['severity'].upper()}] {issue['code']}: {issue['message']}")
    if len(payload["issues"]) > 10:
        print(f"... {len(payload['issues']) - 10} more issue(s)")

    if payload["ok_for_activation"]:
        return 0
    return 0 if args.allow_blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime_binary_locator import resolve_ffmpeg as locate_ffmpeg


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


CREDENTIAL_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "n8n-nodes-base.googleGemini": {
        "provider": "Google Gemini",
        "display_name": "Google Gemini",
        "credential_type": None,
        "credential_type_candidates": ["googlePalmApi", "googleGeminiApi", "googleApi"],
        "credential_type_source": "inferred_from_workflow_node; exact Gemini credential file was not present in the installed n8n-nodes-base package",
        "required_fields": ["apiKey"],
        "optional_fields": [],
    },
    "n8n-nodes-base.openAi": {
        "provider": "OpenAI",
        "display_name": "OpenAI",
        "credential_type": "openAiApi",
        "credential_type_candidates": [],
        "credential_type_source": "installed_n8n_nodes_base",
        "required_fields": ["apiKey"],
        "optional_fields": ["organizationId", "url", "customHeaders"],
    },
}


def credential_requirement_for_node(node_type: str) -> dict[str, Any] | None:
    requirement = CREDENTIAL_REQUIREMENTS.get(node_type)
    if not requirement:
        return None
    return {
        **requirement,
        "credential_type_candidates": list(requirement.get("credential_type_candidates") or []),
        "required_fields": list(requirement.get("required_fields") or []),
        "optional_fields": list(requirement.get("optional_fields") or []),
    }


def _credential_group_key(requirement: dict[str, Any]) -> str:
    credential_type = requirement.get("credential_type")
    if credential_type:
        return f"{requirement.get('provider')}|{credential_type}"
    candidates = ",".join(str(item) for item in requirement.get("credential_type_candidates") or [])
    return f"{requirement.get('provider')}|{candidates}"


def _credential_count(db: dict[str, Any]) -> int:
    try:
        return int((db.get("counts") or {}).get("credentials_entity", 0) or 0)
    except Exception:
        return 0


def build_credential_setup_plan(
    nodes: list[dict[str, Any]] | Any,
    db: dict[str, Any],
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(nodes, list):
        nodes = []
    workflow = workflow or {}
    workflow_id = str(workflow.get("id") or "<workflow-id>")
    credential_count = _credential_count(db)
    groups: dict[str, dict[str, Any]] = {}
    missing_bindings: list[dict[str, Any]] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "")
        requirement = credential_requirement_for_node(node_type)
        if not requirement:
            continue
        key = _credential_group_key(requirement)
        group = groups.setdefault(
            key,
            {
                "provider": requirement["provider"],
                "display_name": requirement["display_name"],
                "credential_type": requirement.get("credential_type"),
                "credential_type_candidates": requirement.get("credential_type_candidates") or [],
                "credential_type_source": requirement["credential_type_source"],
                "required_fields": requirement.get("required_fields") or [],
                "optional_fields": requirement.get("optional_fields") or [],
                "node_types": [],
                "nodes": [],
                "nodes_needing_binding": [],
            },
        )
        if node_type not in group["node_types"]:
            group["node_types"].append(node_type)
        node_name = _node_name(node)
        group["nodes"].append(node_name)
        has_binding = bool(node.get("credentials"))
        if not has_binding:
            group["nodes_needing_binding"].append(node_name)
            missing_bindings.append(
                {
                    "node": node_name,
                    "type": node_type,
                    "provider": requirement["provider"],
                    "credential_type": requirement.get("credential_type"),
                    "credential_type_candidates": requirement.get("credential_type_candidates") or [],
                    "credential_type_source": requirement["credential_type_source"],
                }
            )

    required_credentials = []
    for group in groups.values():
        bind_targets = group["nodes_needing_binding"] or group["nodes"]
        group["ui_steps"] = [
            "Open http://127.0.0.1:5678/credentials.",
            f"Create or select a {group['display_name']} credential.",
            "Enter the provider-owned secret values only in n8n; do not store them in Git.",
            f"Open http://127.0.0.1:5678/workflow/{workflow_id} and bind the credential to: {', '.join(bind_targets)}.",
        ]
        group["verify"] = (
            "Rerun python tools/n8n_workflow_preflight.py --allow-blockers and confirm "
            "missing_node_credentials and n8n_database_has_no_credentials are gone."
        )
        required_credentials.append(group)

    if not required_credentials:
        status = "not_required"
    elif not missing_bindings and credential_count > 0:
        status = "ready"
    else:
        status = "needs_credentials"

    return {
        "status": status,
        "manual_secret_required": status == "needs_credentials",
        "secret_storage_policy": "Store API keys only in the n8n credential store on each machine; never commit secret values to this repository.",
        "credential_count": credential_count,
        "database_available": bool(db.get("ok")),
        "n8n_credentials_url": "http://127.0.0.1:5678/credentials",
        "workflow_url_hint": f"http://127.0.0.1:5678/workflow/{workflow_id}",
        "required_credentials": required_credentials,
        "missing_bindings": missing_bindings,
    }


def remediation_for_issue(issue: Issue) -> dict[str, Any]:
    evidence = issue.evidence or {}
    node = str(evidence.get("node") or "")
    provider = str(evidence.get("provider") or "")
    by_code: dict[str, dict[str, Any]] = {
        "missing_node_credentials": {
            "owner": "operator",
            "manual": True,
            "summary": f"Bind {provider or 'provider'} credentials to {node or 'the provider node'} in n8n.",
            "windows": [
                "Open http://127.0.0.1:5678/credentials",
                "Create or select the provider credential.",
                f"Open workflow node {node or '<node>'} and bind the credential.",
            ],
            "macos": [
                "Open http://127.0.0.1:5678/credentials",
                "Create or select the provider credential.",
                f"Open workflow node {node or '<node>'} and bind the credential.",
            ],
            "verify": "Rerun python tools/n8n_workflow_preflight.py and confirm missing_node_credentials is gone.",
        },
        "n8n_database_has_no_credentials": {
            "owner": "operator",
            "manual": True,
            "summary": "Create at least one provider credential in the n8n credential database.",
            "windows": ["Open http://127.0.0.1:5678/credentials and create the required credentials."],
            "macos": ["Open http://127.0.0.1:5678/credentials and create the required credentials."],
            "verify": "Preflight should report credentials_entity > 0.",
        },
        "ffmpeg_not_found": {
            "owner": "operator",
            "manual": True,
            "summary": "Install FFmpeg or set FFMPEG_PATH to an existing ffmpeg binary.",
            "windows": [
                "winget install Gyan.FFmpeg",
                "Restart the shell after installation.",
                "where ffmpeg",
                "or set FFMPEG_PATH=C:\\path\\to\\ffmpeg.exe before starting n8n.",
                "XIAOBIAN_FFMPEG_PATH is also accepted as a project-specific fallback.",
            ],
            "macos": [
                "brew install ffmpeg",
                "which ffmpeg",
                "or export FFMPEG_PATH=/path/to/ffmpeg before starting n8n.",
                "XIAOBIAN_FFMPEG_PATH is also accepted as a project-specific fallback.",
            ],
            "verify": "Rerun preflight and confirm the report ffmpeg.found is true.",
        },
        "n8n_database_workflow_stale": {
            "owner": "operator",
            "manual": True,
            "summary": "Re-import the hardened source workflow before activation.",
            "windows": [
                "Keep the workflow inactive.",
                "cmd /c n8n import:workflow --input docs\\superpowers\\specs\\n8n-workflow-xiaobian-video.json",
            ],
            "macos": [
                "Keep the workflow inactive.",
                "n8n import:workflow --input docs/superpowers/specs/n8n-workflow-xiaobian-video.json",
            ],
            "verify": "Preflight should no longer report n8n_database_workflow_stale.",
        },
        "workflow_active_before_preflight_clearance": {
            "owner": "operator",
            "manual": True,
            "summary": "Deactivate the workflow until every blocker is cleared.",
            "windows": ["Open n8n workflow settings and switch Active off."],
            "macos": ["Open n8n workflow settings and switch Active off."],
            "verify": "Preflight evidence should show spec_active=false and db_active=false.",
        },
        "placeholder_command": {
            "owner": "developer",
            "manual": False,
            "summary": "Replace placeholder Execute Command text with the hardened FFmpeg wrapper from source control.",
            "windows": ["Edit docs\\superpowers\\specs\\n8n-workflow-xiaobian-video.json, then re-import."],
            "macos": ["Edit docs/superpowers/specs/n8n-workflow-xiaobian-video.json, then re-import."],
            "verify": "Preflight should no longer report placeholder_command.",
        },
        "unsafe_relative_media_paths": {
            "owner": "developer",
            "manual": False,
            "summary": "Use XIAOBIAN_VIDEO_OUTPUT_DIR or data/generated/xiaobian-video instead of bare media filenames.",
            "windows": ["Update the Execute Command node and re-import the workflow."],
            "macos": ["Update the Execute Command node and re-import the workflow."],
            "verify": "Preflight should no longer report unsafe_relative_media_paths.",
        },
        "webhook_without_auth": {
            "owner": "developer",
            "manual": False,
            "summary": "Set the webhook node authentication to headerAuth.",
            "windows": ["Update the source workflow spec and re-import it."],
            "macos": ["Update the source workflow spec and re-import it."],
            "verify": "Preflight should no longer report webhook_without_auth.",
        },
        "webhook_missing_path": {
            "owner": "developer",
            "manual": False,
            "summary": "Set an explicit webhook path in the source workflow spec.",
            "windows": ["Update the webhook node path and re-import the workflow."],
            "macos": ["Update the webhook node path and re-import the workflow."],
            "verify": "Preflight should no longer report webhook_missing_path.",
        },
        "missing_execution_timeout": {
            "owner": "developer",
            "manual": False,
            "summary": "Add settings.executionTimeout to cap runaway workflow execution.",
            "windows": ["Update the source workflow settings and re-import it."],
            "macos": ["Update the source workflow settings and re-import it."],
            "verify": "Preflight should no longer report missing_execution_timeout.",
        },
        "missing_cost_controls": {
            "owner": "developer",
            "manual": False,
            "summary": "Add meta.cost_controls for paid provider nodes.",
            "windows": ["Update the source workflow meta block and re-import it."],
            "macos": ["Update the source workflow meta block and re-import it."],
            "verify": "Preflight should no longer report missing_cost_controls.",
        },
        "missing_error_handling_policy": {
            "owner": "developer",
            "manual": False,
            "summary": "Add settings.errorWorkflow or meta.error_policy.",
            "windows": ["Update the source workflow safety policy and re-import it."],
            "macos": ["Update the source workflow safety policy and re-import it."],
            "verify": "Preflight should no longer report missing_error_handling_policy.",
        },
        "n8n_database_unavailable": {
            "owner": "operator",
            "manual": True,
            "summary": "Start n8n once so its SQLite database can be inspected.",
            "windows": [".\\tools\\start_n8n_windows.cmd"],
            "macos": ["N8N_HOST=127.0.0.1 N8N_PORT=5678 n8n start"],
            "verify": "The configured n8n database path should exist and preflight should read it.",
        },
    }
    plan = by_code.get(
        issue.code,
        {
            "owner": "developer",
            "manual": False,
            "summary": "Inspect this issue and add a specific remediation rule if it recurs.",
            "windows": [],
            "macos": [],
            "verify": "Rerun preflight after remediation.",
        },
    )
    return {"code": issue.code, "severity": issue.severity, **plan, "evidence": evidence}


def build_remediation_plan(issues: list[Issue]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    plan: list[dict[str, Any]] = []
    for issue in issues:
        item = remediation_for_issue(issue)
        key = (str(item.get("code")), str(item.get("summary")))
        if key in seen:
            continue
        seen.add(key)
        plan.append(item)
    return plan


def activation_sequence() -> list[str]:
    return [
        "Keep the workflow inactive while any blocker exists.",
        "Install FFmpeg and verify PATH or FFMPEG_PATH on the target machine.",
        "Follow credential_setup_plan to create provider credentials in n8n and bind them to every provider node.",
        "Re-import the hardened source workflow spec.",
        "Run python tools/n8n_workflow_preflight.py until status is ready_for_activation.",
        "Run one controlled manual execution before enabling unattended automation.",
    ]


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
        "workflow_contract": {},
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
        columns = {
            str(row[1])
            for row in con.execute("pragma table_info(workflow_entity)").fetchall()
        }
        selected = ["id", "name", "active"]
        for column in ("nodes", "settings", "meta"):
            if column in columns:
                selected.append(column)
        row = con.execute(
            f"select {', '.join(selected)} from workflow_entity where id = ? or name = ? limit 1",
            (workflow_id, workflow_name),
        ).fetchone()
        if row:
            raw = dict(row)
            snapshot["workflow"] = {
                "id": raw.get("id"),
                "name": raw.get("name"),
                "active": raw.get("active"),
            }
            snapshot["workflow_contract"] = workflow_contract_snapshot(
                _json_or_default(raw.get("nodes"), []),
                _json_or_default(raw.get("settings"), {}),
                _json_or_default(raw.get("meta"), {}),
            )
        con.close()
        snapshot["ok"] = True
    except Exception as exc:  # noqa: BLE001
        snapshot["error"] = str(exc)
    return snapshot


def _json_or_default(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return default


def workflow_contract_snapshot(
    nodes: list[dict[str, Any]] | Any,
    settings: dict[str, Any] | Any,
    meta: dict[str, Any] | Any,
) -> dict[str, Any]:
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(settings, dict):
        settings = {}
    if not isinstance(meta, dict):
        meta = {}
    webhook_auth = False
    hardened_command = False
    ffmpeg_path_env = False
    ffmpeg_fallback_env = False
    placeholder_command = False
    relative_media_paths = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        params = node.get("parameters") or {}
        node_type = str(node.get("type") or "")
        if node_type == "n8n-nodes-base.webhook":
            webhook_auth = bool(params.get("authentication"))
        if node_type == "n8n-nodes-base.executeCommand":
            command = str(params.get("command") or "")
            hardened_command = (
                "XIAOBIAN_VIDEO_OUTPUT_DIR" in command
                and "data','generated','xiaobian-video" in command
            )
            ffmpeg_path_env = "FFMPEG_PATH" in command
            ffmpeg_fallback_env = "XIAOBIAN_FFMPEG_PATH" in command
            placeholder_command = "..." in command
            relative_media_paths = any(
                token in f" {command} "
                for token in (" image.png", " audio.mp3", " output.mp4")
            )
    return {
        "webhook_auth": webhook_auth,
        "hardened_command": hardened_command,
        "ffmpeg_path_env": ffmpeg_path_env,
        "ffmpeg_fallback_env": ffmpeg_fallback_env,
        "placeholder_command": placeholder_command,
        "relative_media_paths": relative_media_paths,
        "execution_timeout": bool(settings.get("executionTimeout")),
        "cost_controls": bool(meta.get("cost_controls")),
        "error_policy": bool(meta.get("error_policy")),
    }


def _node_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("id") or "<unnamed>")


def audit_credentials(nodes: list[dict[str, Any]], db: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for node in nodes:
        node_type = str(node.get("type") or "")
        requirement = credential_requirement_for_node(node_type)
        if not requirement:
            continue
        if not node.get("credentials"):
            issues.append(
                Issue(
                    "blocker",
                    "missing_node_credentials",
                    f"{_node_name(node)} has no credential binding.",
                    {
                        "node": _node_name(node),
                        "type": node_type,
                        "provider": requirement["provider"],
                        "credential_type": requirement.get("credential_type"),
                        "credential_type_candidates": requirement.get("credential_type_candidates") or [],
                        "credential_type_source": requirement["credential_type_source"],
                    },
                )
            )
    credential_count = _credential_count(db)
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


def resolve_ffmpeg(ffmpeg_path: str | None = None) -> dict[str, Any]:
    return dict(locate_ffmpeg(ffmpeg_path, which=shutil.which))


def audit_execute_commands(
    nodes: list[dict[str, Any]],
    ffmpeg: dict[str, Any] | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    ffmpeg = ffmpeg or resolve_ffmpeg()
    command_nodes = [
        node for node in nodes if str(node.get("type") or "") == "n8n-nodes-base.executeCommand"
    ]
    for node in command_nodes:
        params = node.get("parameters") or {}
        command = str(params.get("command") or "")
        evidence = {"node": _node_name(node), "command": command}
        if "FFMPEG_PATH" not in command:
            issues.append(
                Issue(
                    "warning",
                    "missing_ffmpeg_path_override",
                    "Execute Command node does not support FFMPEG_PATH override.",
                    evidence,
                )
            )
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
        if not ffmpeg.get("found"):
            issues.append(
                Issue(
                    "blocker",
                    "ffmpeg_not_found",
                    "ffmpeg is not available through PATH, FFMPEG_PATH, or XIAOBIAN_FFMPEG_PATH for the Execute Command node.",
                    {"node": _node_name(node), "ffmpeg": ffmpeg},
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


def audit_db_workflow_contract(db: dict[str, Any]) -> list[Issue]:
    workflow = db.get("workflow") or {}
    if not db.get("ok") or not workflow:
        return []
    contract = db.get("workflow_contract") or {}
    stale = []
    expected = {
        "webhook_auth": True,
        "hardened_command": True,
        "ffmpeg_path_env": True,
        "ffmpeg_fallback_env": True,
        "placeholder_command": False,
        "relative_media_paths": False,
        "execution_timeout": True,
        "cost_controls": True,
        "error_policy": True,
    }
    for key, expected_value in expected.items():
        if contract.get(key) != expected_value:
            stale.append(key)
    if not stale:
        return []
    return [
        Issue(
            "blocker",
            "n8n_database_workflow_stale",
            "The workflow imported in n8n DB does not match the hardened source spec; re-import before activation.",
            {
                "workflow": workflow,
                "stale_contracts": stale,
                "contract": contract,
            },
        )
    ]


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


def run_preflight(
    spec_path: Path,
    db_path: Path,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    ffmpeg = resolve_ffmpeg(ffmpeg_path)
    workflow, issues = load_workflow(spec_path)
    if workflow is None:
        blockers = [issue for issue in issues if issue.severity == "blocker"]
        credential_setup_plan = build_credential_setup_plan(
            [],
            {"path": str(db_path), "exists": db_path.exists(), "ok": False, "counts": {}},
        )
        return {
            "ok_for_activation": False,
            "status": "invalid",
            "spec_path": str(spec_path),
            "ffmpeg": ffmpeg,
            "db": {"path": str(db_path), "exists": db_path.exists()},
            "issues": [asdict(issue) for issue in issues],
            "credential_setup_plan": credential_setup_plan,
            "remediation_plan": build_remediation_plan(issues),
            "activation_sequence": activation_sequence(),
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
    issues.extend(audit_execute_commands(nodes, ffmpeg))
    issues.extend(audit_webhooks(nodes))
    issues.extend(audit_safety(workflow, db))
    issues.extend(audit_db_workflow_contract(db))
    credential_setup_plan = build_credential_setup_plan(nodes, db, workflow)

    blockers = [issue for issue in issues if issue.severity == "blocker"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return {
        "ok_for_activation": not blockers,
        "status": "ready_for_activation" if not blockers else "blocked_for_activation",
        "spec_path": str(spec_path),
        "ffmpeg": ffmpeg,
        "workflow": {
            "id": workflow.get("id", ""),
            "name": workflow.get("name", ""),
            "active": bool(workflow.get("active")),
            "node_count": len(nodes),
        },
        "db": db,
        "issues": [asdict(issue) for issue in issues],
        "credential_setup_plan": credential_setup_plan,
        "remediation_plan": build_remediation_plan(issues),
        "activation_sequence": activation_sequence(),
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
        "--ffmpeg-path",
        default="",
        help="Optional explicit ffmpeg binary path; also supports FFMPEG_PATH or XIAOBIAN_FFMPEG_PATH.",
    )
    parser.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Return 0 even when activation blockers are found; useful for inventory health checks.",
    )
    args = parser.parse_args()

    payload = run_preflight(Path(args.workflow_spec), Path(args.db), args.ffmpeg_path or None)
    write_report(payload, Path(args.json_out))

    print("== n8n Workflow Preflight ==")
    print(f"workflow: {payload.get('workflow', {}).get('name', args.workflow_spec)}")
    print(f"status: {payload['status']}")
    print(f"blockers: {payload['blocker_count']} warnings: {payload['warning_count']}")
    for issue in payload["issues"][:10]:
        print(f"[{issue['severity'].upper()}] {issue['code']}: {issue['message']}")
    if len(payload["issues"]) > 10:
        print(f"... {len(payload['issues']) - 10} more issue(s)")
    remediation = payload.get("remediation_plan") or []
    credential_setup = payload.get("credential_setup_plan") or {}
    if credential_setup:
        print(f"credential_setup: {credential_setup.get('status', 'unknown')}")
    if remediation:
        print("remediation:")
        for item in remediation[:5]:
            print(f"- {item['code']}: {item['summary']}")
        if len(remediation) > 5:
            print(f"... {len(remediation) - 5} more remediation item(s)")

    if payload["ok_for_activation"]:
        return 0
    return 0 if args.allow_blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())

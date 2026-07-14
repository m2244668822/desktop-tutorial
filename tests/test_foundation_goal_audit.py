import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "foundation_goal_audit.py"
SPEC = importlib.util.spec_from_file_location("foundation_goal_audit", MODULE_PATH)
foundation_goal_audit = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["foundation_goal_audit"] = foundation_goal_audit
SPEC.loader.exec_module(foundation_goal_audit)


def check(name, ok=True, status="ready", detail=None):
    return {"name": name, "ok": ok, "status": status, "detail": detail or {}}


def openclaw_ready_check():
    return check(
        "openclaw_runtime",
        True,
        "ready",
        {
            "health": "ready",
            "gateway": {"listening": True, "health_ok": True},
            "governance": {"decision_state": "running"},
            "local_execution": {
                "supported": True,
                "criteria": {
                    "cli_installed": True,
                    "gateway_listening": True,
                    "gateway_health_ok": True,
                },
            },
        },
    )


def preflight_ready_check():
    return check(
        "n8n_workflow_preflight",
        True,
        "ready_for_activation",
        {
            "report": {
                "status": "ready_for_activation",
                "ok_for_activation": True,
                "blocker_count": 0,
                "credential_setup_plan": {"status": "ready"},
                "issues": [],
            }
        },
    )


def base_health(preflight=None, include_browser=True, git_status=None):
    checks = [
        check("workspace_context"),
        check("runtime_dependencies"),
        check("runtime_service_controller"),
        check(
            "repo_secret_hygiene",
            True,
            "ready",
            {
                "report_path": "reports/repo_secret_hygiene_latest.json",
                "report": {
                    "finding_count": 0,
                    "gitignore": {"ok": True, "missing": []},
                },
            },
        ),
        check("ports"),
        check("gateway"),
        openclaw_ready_check(),
        check("n8n"),
        preflight or preflight_ready_check(),
        check("knowledge_hub"),
        check("frontend_static_contract"),
        check(
            "git",
            True,
            "dirty" if git_status else "ready",
            {"status": git_status or ["## branch"]},
        ),
        check("py_compile"),
    ]
    if include_browser:
        checks.append(
            check(
                "browser_smoke",
                True,
                "ready",
                {
                    "viewports": [
                        {"name": "mobile", "width": 390, "height": 844, "ok": True, "status": "ready"},
                        {"name": "tablet", "width": 768, "height": 1024, "ok": True, "status": "ready"},
                        {"name": "desktop", "width": 1440, "height": 1000, "ok": True, "status": "ready"},
                    ]
                },
            )
        )
    return {"checks": checks, "next_actions": []}


class FoundationGoalAuditTests(unittest.TestCase):
    def test_goal_audit_marks_n8n_credentials_blocker_incomplete(self):
        preflight = check(
            "n8n_workflow_preflight",
            True,
            "blocked_for_activation",
            {
                "report": {
                    "status": "blocked_for_activation",
                    "ok_for_activation": False,
                    "blocker_count": 4,
                    "credential_setup_plan": {"status": "needs_credentials"},
                    "issues": [{"code": "missing_node_credentials"}],
                }
            },
        )
        health = base_health(
            preflight=preflight,
            git_status=["## branch", " M reports/AEG_SHARED_REPORT.md"],
        )

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["status"], "incomplete")
        by_id = {item["id"]: item for item in audit["requirements"]}
        self.assertEqual(by_id["n8n_activation_ready"]["status"], "blocked")
        self.assertEqual(by_id["optimization_flow_no_sprawl"]["status"], "passed")
        self.assertEqual(by_id["repo_secret_hygiene_ready"]["status"], "passed")
        self.assertFalse(audit["completion_claim_allowed"])
        self.assertEqual(audit["completion_blocker_summary"]["by_category"]["external_credentials_required"], 1)
        self.assertTrue(audit["completion_blocker_summary"]["operator_required"])
        self.assertTrue(audit["completion_blocker_summary"]["external_dependency"])
        self.assertEqual(audit["completion_blockers"][0]["category"], "external_credentials_required")

    def test_goal_audit_marks_n8n_manual_execution_incomplete(self):
        preflight = check(
            "n8n_workflow_preflight",
            True,
            "ready_for_manual_execution",
            {
                "report": {
                    "status": "ready_for_manual_execution",
                    "ok_for_activation": False,
                    "blocker_count": 0,
                    "credential_setup_plan": {"status": "ready"},
                    "manual_execution_plan": {"status": "needs_manual_execution"},
                    "issues": [],
                }
            },
        )
        health = base_health(preflight=preflight)

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["status"], "incomplete")
        by_id = {item["id"]: item for item in audit["requirements"]}
        self.assertEqual(by_id["n8n_activation_ready"]["status"], "incomplete")
        self.assertEqual(
            by_id["n8n_activation_ready"]["evidence"]["manual_execution_plan"]["status"],
            "needs_manual_execution",
        )
        self.assertFalse(audit["completion_claim_allowed"])
        self.assertEqual(audit["completion_blockers"][0]["category"], "manual_execution_required")
        self.assertTrue(audit["completion_blockers"][0]["operator_required"])
        self.assertFalse(audit["completion_blockers"][0]["external_dependency"])

    def test_goal_audit_requires_real_browser_smoke_evidence(self):
        health = base_health(include_browser=False)

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        by_id = {item["id"]: item for item in audit["requirements"]}
        self.assertEqual(by_id["frontend_issue_free"]["status"], "missing_evidence")
        self.assertIn("browser_smoke", by_id["frontend_issue_free"]["evidence"]["missing"])

    def test_goal_audit_requires_browser_smoke_viewport_matrix(self):
        health = base_health()
        for item in health["checks"]:
            if item["name"] == "browser_smoke":
                item["detail"] = {
                    "viewports": [
                        {"name": "desktop", "width": 1440, "height": 1000, "ok": True, "status": "ready"}
                    ]
                }

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        by_id = {item["id"]: item for item in audit["requirements"]}
        self.assertEqual(by_id["frontend_issue_free"]["status"], "incomplete")
        self.assertIn("browser_smoke_matrix", by_id["frontend_issue_free"]["evidence"]["failing"])

    def test_goal_audit_includes_backend_diagnostic_matrix_evidence(self):
        health = base_health()
        health["diagnostic_matrix"] = [
            {"id": "gateway_backend", "status": "ready"},
            {"id": "automation_n8n", "status": "attention_required"},
            {"id": "frontend_runtime", "status": "ready"},
        ]

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        by_id = {item["id"]: item for item in audit["requirements"]}
        matrix = by_id["backend_multi_angle_detection"]["evidence"]["diagnostic_matrix"]
        self.assertEqual([item["id"] for item in matrix], ["gateway_backend", "automation_n8n"])

    def test_goal_audit_requires_repo_secret_hygiene(self):
        health = base_health()
        health["checks"] = [
            item for item in health["checks"] if item["name"] != "repo_secret_hygiene"
        ]

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        by_id = {item["id"]: item for item in audit["requirements"]}
        self.assertEqual(by_id["repo_secret_hygiene_ready"]["status"], "missing_evidence")
        self.assertFalse(audit["completion_claim_allowed"])

    def test_goal_audit_passes_when_all_requirements_are_ready(self):
        health = base_health()

        audit = foundation_goal_audit.build_audit(health, Path("health.json"))

        self.assertTrue(audit["ok"])
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(audit["passed_count"], audit["requirement_count"])
        self.assertTrue(audit["completion_claim_allowed"])
        self.assertEqual(audit["completion_blocker_summary"]["count"], 0)
        self.assertEqual(audit["completion_blockers"], [])


if __name__ == "__main__":
    unittest.main()

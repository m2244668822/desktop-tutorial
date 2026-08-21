import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.agent_collaboration_audit import (
    AUDIT_RELATIVE_PATH,
    TRAINING_RULES,
    record_agent_collaboration_event,
)
from tools.generate_agent_collaboration_review import build_markdown


class AgentCollaborationTrainingContractTests(unittest.TestCase):
    def test_training_rules_cover_avoid_repeat_contract(self):
        expected = {
            "ENTRY_CHECK_ORDER",
            "OPENCLAW_FALLBACK_REQUIRED",
            "N8N_OPTIONAL_ONLY",
            "AUDIT_EVERY_REPAIR",
            "PYTHON_RUNTIME_RISK",
        }

        self.assertTrue(expected.issubset(TRAINING_RULES.keys()))
        self.assertEqual(TRAINING_RULES["ENTRY_CHECK_ORDER"]["owner"], "工程師")
        self.assertIn("5001", TRAINING_RULES["ENTRY_CHECK_ORDER"]["description"])

    def test_audit_event_accepts_training_overlay_fields(self):
        with tempfile.TemporaryDirectory() as td:
            event = record_agent_collaboration_event(
                td,
                task_goal="避免重犯規則訓練",
                agent="總管中樞",
                route="training_overlay",
                decision="將規則寫入審計",
                outcome="training_required",
                remedy="建立規則與分工",
                score_delta=-10,
                rule_ids=["ENTRY_CHECK_ORDER", "AUDIT_EVERY_REPAIR"],
                assigned_agents=["工程師", "總管中樞"],
                severity="medium",
                learning_action="資料層訓練，不覆蓋原本對話模式",
                training_tags=["entry_stability", "audit_learning"],
                evidence={"source": "user_rule"},
                next_guardrail="入口問題必須先測 5001 再測 5443",
            )

            rows = (Path(td) / AUDIT_RELATIVE_PATH).read_text(encoding="utf-8").splitlines()
            payload = json.loads(rows[-1])

        self.assertEqual(event["score_delta"], -10)
        self.assertEqual(payload["rule_ids"], ["ENTRY_CHECK_ORDER", "AUDIT_EVERY_REPAIR"])
        self.assertEqual(payload["assigned_agents"], ["工程師", "總管中樞"])
        self.assertEqual(payload["severity"], "medium")
        self.assertIn("entry_stability", payload["training_tags"])
        self.assertEqual(payload["evidence"]["source"], "user_rule")

    def test_review_renders_rules_assignments_and_learning_fields(self):
        events = [
            {
                "created_at": "2026-06-06T12:00:00",
                "task_goal": "避免重犯規則訓練",
                "agent": "總管中樞",
                "route": "training_overlay",
                "decision": "將規則寫入審計",
                "outcome": "training_required",
                "remedy": "建立規則與分工",
                "score_delta": -10,
                "rule_ids": ["ENTRY_CHECK_ORDER", "OPENCLAW_FALLBACK_REQUIRED"],
                "assigned_agents": ["工程師", "總管中樞"],
                "learning_action": "強化入口與回退判斷",
                "training_tags": ["entry_stability", "openclaw_fallback"],
                "next_guardrail": "OpenClaw 無可讀回覆必須回退 DesktopBridge",
            }
        ]

        markdown = build_markdown(events, Path("/tmp/workspace"))

        self.assertIn("ENTRY_CHECK_ORDER", markdown)
        self.assertIn("工程師、總管中樞", markdown)
        self.assertIn("強化入口與回退判斷", markdown)
        self.assertIn("OpenClaw 無可讀回覆必須回退 DesktopBridge", markdown)
        self.assertIn("entry_stability", markdown)

    def test_review_passes_markdownlint_contract(self):
        markdownlint = shutil.which("markdownlint")
        if markdownlint is None:
            self.skipTest("markdownlint is not installed")

        events = [
            {
                "created_at": "2026-06-06T12:00:00",
                "agent": "總管中樞",
                "route": "training_overlay",
                "decision": "將規則寫入審計",
                "outcome": "training_required",
                "remedy": "建立規則與分工",
                "score_delta": -10,
                "rule_ids": ["ENTRY_CHECK_ORDER", "OPENCLAW_FALLBACK_REQUIRED"],
                "assigned_agents": ["工程師", "總管中樞"],
                "learning_action": "強化入口與回退判斷",
                "training_tags": ["entry_stability", "openclaw_fallback"],
                "next_guardrail": "OpenClaw 無可讀回覆必須回退 DesktopBridge",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "agent_collaboration_review.md"
            report.write_text(
                build_markdown(events, Path("/tmp/workspace")),
                encoding="utf-8",
            )
            result = subprocess.run(
                [markdownlint, str(report)],
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

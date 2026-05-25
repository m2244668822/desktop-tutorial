import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / ".sync_user_project" / "templates" / "chat.html"


class FrontendSyncContractTests(unittest.TestCase):
    def setUp(self):
        self.html = CHAT_HTML.read_text(encoding="utf-8")

    def test_tasks_panel_defaults_to_unresolved_filter(self):
        self.assertIn('let _tasksFilter = "unresolved";', self.html)
        self.assertIn('key: "unresolved"', self.html)
        self.assertIn("label: \"未解\"", self.html)

    def test_sync_after_chat_respects_provider_rate_limit_gap(self):
        self.assertRegex(
            self.html,
            r"syncAfterChat[\s\S]*await fetchProviderStatus\(false\);",
        )

    def test_provider_polling_and_backoff_guard_exist(self):
        self.assertIn("provider: 900000", self.html)
        self.assertIn("provider: 180000", self.html)
        self.assertIn("const PROVIDER_RATE_LIMIT_BACKOFF_MS = 1800000;", self.html)
        self.assertIn("if (r.status === 429)", self.html)
        self.assertIn("blockedUntil", self.html)
        self.assertIn("觸發限流，已暫停狀態更新 30 分鐘", self.html)

    def test_unresolved_view_sorts_running_failed_then_pending(self):
        self.assertIn('if (_tasksFilter === "unresolved") {', self.html)
        self.assertIn("const priority = { running: 0, failed: 1, pending: 2 };", self.html)
        self.assertIn("normalizedItems.sort((a, b) => {", self.html)
        self.assertIn("return bt - at;", self.html)

    def test_agent_activity_board_contract_present(self):
        self.assertIn('id="agentActivityBoard"', self.html)
        self.assertIn('id="agentActivityMeta"', self.html)
        self.assertIn("function renderAgentActivityBoard()", self.html)
        self.assertIn("renderAgentActivityBoard();", self.html)
        self.assertIn('fetch("/agent/tasks?status=running&limit=120&compact=1"', self.html)
        self.assertIn('fetch("/agent/tasks?status=pending&limit=120&compact=1"', self.html)
        self.assertRegex(
            self.html,
            r"function _setBusy\(busy\)[\s\S]*renderAgentActivityBoard\(\);",
        )

    def test_thinking_phase_breakdown_present(self):
        self.assertIn("function setThinkingPhase(", self.html)
        self.assertIn("function getThinkingPhaseLabel()", self.html)
        self.assertIn("等待模型回覆", self.html)
        self.assertIn("本地整理回覆", self.html)
        self.assertIn("正在重試", self.html)
        self.assertIn("setThinkingPhase(\"waiting\")", self.html)
        self.assertIn("setThinkingPhase(\"processing\")", self.html)
        self.assertIn("setThinkingPhase(\"retrying\"", self.html)
        self.assertIn("async function _fetchWithRetry(url, options, maxRetries = 1, delayMs = 1500, hooks = {})", self.html)


if __name__ == "__main__":
    unittest.main()

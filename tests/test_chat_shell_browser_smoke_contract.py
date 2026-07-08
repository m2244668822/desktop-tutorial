import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "chat_shell_browser_smoke.py"
SPEC = importlib.util.spec_from_file_location("chat_shell_browser_smoke", MODULE_PATH)
chat_shell_browser_smoke = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["chat_shell_browser_smoke"] = chat_shell_browser_smoke
SPEC.loader.exec_module(chat_shell_browser_smoke)


class ChatShellBrowserSmokeContractTests(unittest.TestCase):
    def test_text_integrity_uses_dom_text_for_hidden_mobile_panel_copy(self):
        expression = chat_shell_browser_smoke.DOM_AUDIT_EXPRESSION

        self.assertIn("const visibleText = document.body.innerText || \"\";", expression)
        self.assertIn("const domText = document.body.textContent || \"\";", expression)
        self.assertIn(
            "requiredText: Object.fromEntries(requiredText.map(token => [token, domText.includes(token)]))",
            expression,
        )
        self.assertIn("bodyTextLength: visibleText.length", expression)
        self.assertIn("domTextLength: domText.length", expression)


if __name__ == "__main__":
    unittest.main()

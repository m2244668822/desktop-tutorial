import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "data_summary_20260426_frontend_backend.md"


class ReportMarkdownTableTests(unittest.TestCase):
    def test_table_separator_pipes_have_spaces(self):
        text = REPORT.read_text(encoding="utf-8")
        separator_row = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$", re.MULTILINE)
        for match in separator_row.finditer(text):
            line = match.group(0)
            with self.subTest(line=line):
                self.assertNotRegex(line, r"\|[-:]")
                self.assertNotRegex(line, r"[-:]\|")


if __name__ == "__main__":
    unittest.main()

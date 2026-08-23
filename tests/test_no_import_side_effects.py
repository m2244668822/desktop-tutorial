import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestImportSideEffects(unittest.TestCase):
    def test_tests_do_not_execute_work_at_import_time(self):
        offenders = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, ast.Expr) and self._is_call_named(node.value, "print"):
                    offenders.append(f"{path.name}:{node.lineno}: top-level print()")
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    call_name = self._call_name(node.value.func)
                    if call_name in {"LocalMemoryAPI", "NeuroHub"}:
                        offenders.append(
                            f"{path.name}:{node.lineno}: top-level {call_name}()"
                        )

        self.assertEqual([], offenders)

    @staticmethod
    def _is_call_named(node, name: str) -> bool:
        return isinstance(node, ast.Call) and TestImportSideEffects._call_name(node.func) == name

    @staticmethod
    def _call_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""


if __name__ == "__main__":
    unittest.main()

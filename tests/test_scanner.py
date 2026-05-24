"""Tests for agent/scanner.py"""
import ast
import textwrap
import unittest
from unittest.mock import MagicMock, patch

from agent.scanner import Scanner


def make_cfg():
    cfg = MagicMock()
    cfg.debt_rules_path = "rules/debt_rules.yaml"
    cfg.github_token = "fake-token"
    return cfg


class TestScannerDetectors(unittest.TestCase):
    def setUp(self):
        with patch("agent.scanner.Path.exists", return_value=False):
            self.scanner = Scanner("org/repo", make_cfg())

    def _tree(self, src: str) -> ast.AST:
        return ast.parse(textwrap.dedent(src))

    def test_detect_short_function_name(self):
        tree = self._tree("def ab(): pass")
        issues = self.scanner._detect_naming(tree, "test.py")
        self.assertTrue(any(i["type"] == "naming" for i in issues))

    def test_no_issue_for_long_name(self):
        tree = self._tree("def my_function(): pass")
        issues = self.scanner._detect_naming(tree, "test.py")
        self.assertEqual(issues, [])

    def test_detect_high_complexity(self):
        # Build a function with many branches
        src = """
def complex_func(x):
    if x:
        for i in range(10):
            while i:
                if i > 5:
                    if i > 7:
                        if i > 9:
                            pass
                        else:
                            pass
    return x
"""
        tree = self._tree(src)
        self.scanner.rules["max_complexity"] = 3
        issues = self.scanner._detect_complexity(tree, "test.py", src)
        self.assertTrue(any(i["type"] == "complexity" for i in issues))

    def test_detect_missing_type_annotation(self):
        tree = self._tree("def my_func(x): return x")
        issues = self.scanner._detect_missing_type_annotations(tree, "test.py")
        self.assertTrue(any(i["type"] == "type_annotation" for i in issues))

    def test_no_annotation_issue_for_private(self):
        tree = self._tree("def _private(x): return x")
        issues = self.scanner._detect_missing_type_annotations(tree, "test.py")
        self.assertEqual(issues, [])

    def test_detect_dead_import(self):
        src = "import os\nx = 1"
        tree = self._tree(src)
        issues = self.scanner._detect_dead_imports(tree, "test.py", src)
        self.assertTrue(any(i["type"] == "dead_import" for i in issues))

    def test_cyclomatic_complexity_simple(self):
        tree = self._tree("def f(): return 1")
        func_node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        cc = self.scanner._cyclomatic_complexity(func_node)
        self.assertEqual(cc, 1)


if __name__ == "__main__":
    unittest.main()

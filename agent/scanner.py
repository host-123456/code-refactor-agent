"""
scanner.py
Stage 1: Scan a cloned repo for tech debt using AST analysis + rule engine.
Returns a structured JSON debt manifest.
"""
import ast
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

SEVERITY = {"naming": 2, "complexity": 4, "dry": 3, "type_annotation": 1, "dead_import": 2}


class Scanner:
    def __init__(self, repo: str, cfg):
        self.repo = repo
        self.cfg = cfg
        self.rules = self._load_rules()

    def _load_rules(self) -> dict:
        path = Path(self.cfg.debt_rules_path)
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
        return {"max_complexity": 10, "min_name_length": 3}

    def scan(self) -> list[dict[str, Any]]:
        """Clone the repo and run all detectors. Returns debt manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_url = f"https://{self.cfg.github_token}@github.com/{self.repo}.git"
            subprocess.run(["git", "clone", "--depth", "1", clone_url, tmpdir],
                           check=True, capture_output=True)
            return self._scan_directory(tmpdir)

    def _scan_directory(self, root: str) -> list[dict]:
        manifest = []
        for py_file in Path(root).rglob("*.py"):
            if any(p in str(py_file) for p in ["venv", ".git", "__pycache__", "test_"]):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
                rel_path = str(py_file.relative_to(root))
                manifest.extend(self._detect_naming(tree, rel_path))
                manifest.extend(self._detect_complexity(tree, rel_path, source))
                manifest.extend(self._detect_missing_type_annotations(tree, rel_path))
                manifest.extend(self._detect_dead_imports(tree, rel_path, source))
            except SyntaxError:
                log.warning(f"Skipping unparseable file: {py_file}")
        return manifest

    def _detect_naming(self, tree: ast.AST, path: str) -> list[dict]:
        issues = []
        min_len = self.rules.get("min_name_length", 3)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if len(node.name) < min_len and node.name not in ("__init__", "run", "go"):
                    issues.append({
                        "type": "naming",
                        "severity": SEVERITY["naming"],
                        "file": path,
                        "line": node.lineno,
                        "message": f"Function name '{node.name}' is too short (min {min_len} chars)",
                        "context": f"def {node.name}(...)"
                    })
        return issues

    def _detect_complexity(self, tree: ast.AST, path: str, source: str) -> list[dict]:
        issues = []
        max_cc = self.rules.get("max_complexity", 10)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = self._cyclomatic_complexity(node)
                if cc > max_cc:
                    lines = source.splitlines()
                    ctx = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                    issues.append({
                        "type": "complexity",
                        "severity": SEVERITY["complexity"],
                        "file": path,
                        "line": node.lineno,
                        "message": f"Function '{node.name}' has cyclomatic complexity {cc} (max {max_cc})",
                        "context": ctx
                    })
        return issues

    def _cyclomatic_complexity(self, node: ast.AST) -> int:
        """Count branches: if, elif, for, while, except, with, assert, comprehensions."""
        branch_nodes = (ast.If, ast.For, ast.While, ast.ExceptHandler,
                        ast.With, ast.Assert, ast.comprehension)
        return 1 + sum(1 for n in ast.walk(node) if isinstance(n, branch_nodes))

    def _detect_missing_type_annotations(self, tree: ast.AST, path: str) -> list[dict]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is None and not node.name.startswith("_"):
                    issues.append({
                        "type": "type_annotation",
                        "severity": SEVERITY["type_annotation"],
                        "file": path,
                        "line": node.lineno,
                        "message": f"Function '{node.name}' is missing a return type annotation",
                        "context": f"def {node.name}(...) -> ?"
                    })
        return issues

    def _detect_dead_imports(self, tree: ast.AST, path: str, source: str) -> list[dict]:
        issues = []
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names.add((name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names.add((name, node.lineno))

        for name, lineno in imported_names:
            # Simple heuristic: count occurrences beyond the import line
            occurrences = source.count(name)
            if occurrences <= 1:
                issues.append({
                    "type": "dead_import",
                    "severity": SEVERITY["dead_import"],
                    "file": path,
                    "line": lineno,
                    "message": f"Imported name '{name}' appears unused",
                    "context": f"import {name}"
                })
        return issues

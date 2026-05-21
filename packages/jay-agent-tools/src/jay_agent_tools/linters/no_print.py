"""JC001 — detect raw `print(...)` calls outside tests."""

from __future__ import annotations

import ast
from pathlib import Path

from .base import LintFinding


class NoPrintLinter:
    code = "JC001"
    name = "no-print"

    def check(self, file: Path, source: str) -> list[LintFinding]:
        if "tests" in file.parts or file.name.startswith("test_"):
            return []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        # Pre-scan source lines for `# noqa: JC001` escape hatches.
        source_lines = source.splitlines()
        noqa_lines: set[int] = {
            i + 1
            for i, line in enumerate(source_lines)
            if "# noqa: JC001" in line or "# noqa:JC001" in line
        }

        findings: list[LintFinding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                if node.lineno in noqa_lines:
                    continue
                findings.append(
                    LintFinding(
                        file=file,
                        line=node.lineno,
                        code=self.code,
                        message="Raw print() call in non-test code.",
                        suggestion=(
                            "改用 logger.debug() / logger.info() 进行日志记录；"
                            "确需保留时加 `# noqa: JC001` 注释。"
                        ),
                        autofix=None,
                    )
                )
        return findings

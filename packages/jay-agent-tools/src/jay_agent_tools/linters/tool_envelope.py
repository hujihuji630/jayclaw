"""JC002 — tool handlers must wrap return values in ToolResult."""

from __future__ import annotations

import ast
from pathlib import Path

from .base import LintFinding


def _is_tool_decorated(func: ast.AST) -> bool:
    """Heuristic: function decorated with @tool / @_register / @register_tool."""
    if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    for deco in func.decorator_list:
        if isinstance(deco, ast.Name) and deco.id in {"tool", "_register", "register_tool"}:
            return True
        if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name):
            if deco.func.id in {"tool", "_register", "register_tool"}:
                return True
        if isinstance(deco, ast.Attribute) and deco.attr in {"tool", "register_tool"}:
            return True
    return False


def _returns_tool_result(node: ast.Return) -> bool:
    """True if `return ToolResult(...)` or `return SomeName` (likely already wrapped)."""
    val = node.value
    if val is None:
        return True  # bare `return` is fine; not a literal
    if isinstance(val, ast.Call):
        func = val.func
        if isinstance(func, ast.Name) and func.id == "ToolResult":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "ToolResult":
            return True
        if isinstance(func, ast.Name) and func.id.startswith("_"):
            return True
    if isinstance(val, ast.Await) and isinstance(val.value, ast.Call):
        f = val.value.func
        if isinstance(f, ast.Name) and f.id == "ToolResult":
            return True
        if isinstance(f, ast.Attribute) and f.attr == "ToolResult":
            return True
    if isinstance(val, ast.Name | ast.Attribute):
        return True
    return False


class ToolEnvelopeLinter:
    code = "JC002"
    name = "tool-envelope"

    def check(self, file: Path, source: str) -> list[LintFinding]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        findings: list[LintFinding] = []
        for node in ast.walk(tree):
            if not _is_tool_decorated(node):
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Return):
                    continue
                if _returns_tool_result(sub):
                    continue
                if not isinstance(sub.value, ast.Dict | ast.List | ast.Constant | ast.JoinedStr):
                    continue
                findings.append(
                    LintFinding(
                        file=file,
                        line=sub.lineno,
                        code=self.code,
                        message=(
                            "Tool handler returns raw literal instead of ToolResult."
                        ),
                        suggestion=(
                            "用 ToolResult(ok=True, data=...) 包装返回值；"
                            "失败路径用 ToolResult(ok=False, error='...')。"
                        ),
                        autofix=None,
                    )
                )
        return findings

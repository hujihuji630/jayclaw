"""JC004 — pinyin identifier names (stub).

The full pinyin dictionary lives in
`jay_agent_tools.web.handlers._PINYIN_WORDS`. This linter delegates to that
mapping when available so that the lint catalog and the runtime tool stay
in sync. If the mapping cannot be imported, returns an empty list.

TODO: 待 P1 完整实现拼音词典本地化（避免对 web.handlers 的隐式依赖）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from .base import LintFinding


def _load_dictionary() -> tuple[set[str], dict[str, str]]:
    try:
        from jay_agent_tools.web.handlers import _PINYIN_WORDS, _SUGGESTIONS

        return set(_PINYIN_WORDS), dict(_SUGGESTIONS)
    except Exception:
        return set(), {}


class PinyinNamingLinter:
    code = "JC004"
    name = "pinyin-naming"

    def __init__(self) -> None:
        self._words, self._suggestions = _load_dictionary()

    def check(self, file: Path, source: str) -> list[LintFinding]:
        if not self._words:
            return []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        seen: set[tuple[str, int]] = set()
        findings: list[LintFinding] = []
        for node in ast.walk(tree):
            name: str | None = None
            line: int | None = None
            if isinstance(node, ast.Name):
                name, line = node.id, node.lineno
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name, line = node.name, node.lineno
            elif isinstance(node, ast.arg):
                name, line = node.arg, node.lineno
            if not name or not line:
                continue
            if (name, line) in seen or len(name) < 3:
                continue
            seen.add((name, line))
            if name not in self._words:
                continue
            english = self._suggestions.get(name, "english_name")
            findings.append(
                LintFinding(
                    file=file,
                    line=line,
                    code=self.code,
                    message=f"Identifier '{name}' looks like a pinyin word.",
                    suggestion=f"改用英文命名，例：{name} → {english}",
                    autofix=english,
                )
            )
        return findings

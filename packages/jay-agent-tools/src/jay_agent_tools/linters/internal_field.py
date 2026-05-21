"""JC003 — tool schema fields used only internally must start with `_`.

Heuristic: when a `properties` dict (inside a schema) contains a key whose
identifier looks like an internal marker (e.g. `internal`, `skip_llm`,
`activate`, `permission`, `_meta`-style name without underscore prefix),
suggest renaming with a leading underscore so `strip_internal_fields`
removes it before the schema reaches the LLM.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .base import LintFinding

_INTERNAL_MARKERS = {
    "internal",
    "skip_llm",
    "activate",
    "permission",
    "private",
    "system_only",
    "agent_only",
}


def _is_properties_assignment(node: ast.AST) -> ast.Dict | None:
    """Detect a dict literal that resembles a JSON schema's `properties`."""
    if isinstance(node, ast.Dict):
        # Direct dict literal
        return node
    return None


class InternalFieldLinter:
    code = "JC003"
    name = "internal-field"

    def check(self, file: Path, source: str) -> list[LintFinding]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        findings: list[LintFinding] = []
        for node in ast.walk(tree):
            # Look for `"properties": { ... }` pairs in any dict literal.
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                if not isinstance(key, ast.Constant) or key.value != "properties":
                    continue
                inner = _is_properties_assignment(value)
                if inner is None:
                    continue
                for prop_key in inner.keys:
                    if not isinstance(prop_key, ast.Constant):
                        continue
                    prop_name = str(prop_key.value)
                    lowered = prop_name.lower()
                    if lowered.startswith("_"):
                        continue
                    if lowered in _INTERNAL_MARKERS:
                        findings.append(
                            LintFinding(
                                file=file,
                                line=prop_key.lineno,
                                code=self.code,
                                message=(
                                    f"Schema property '{prop_name}' looks internal "
                                    f"but is missing the `_` prefix."
                                ),
                                suggestion=(
                                    f"字段名前加 `_` 前缀（改为 '_{prop_name}'），"
                                    "会被 strip_internal_fields 自动从 LLM 视野中剥离。"
                                ),
                                autofix=f'"_{prop_name}"',
                            )
                        )
        return findings

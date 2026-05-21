"""Base types for custom Agent-friendly linters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LintFinding:
    """A single lint finding.

    The `suggestion` field is what makes this Agent-friendly: it must tell
    the reader HOW to fix, not just what is wrong. Empty suggestions are
    rejected at construction time.
    """

    file: Path
    line: int
    code: str
    message: str
    suggestion: str
    autofix: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.suggestion, str) or not self.suggestion.strip():
            raise ValueError(
                f"LintFinding.suggestion must be a non-empty string "
                f"(code={self.code!r}, file={self.file})"
            )

    def render(self) -> str:
        """Render as a single-line human-readable string."""
        s = f"{self.file}:{self.line} [{self.code}] {self.message}\n  → {self.suggestion}"
        if self.autofix:
            s += f"\n  ✎ autofix: {self.autofix}"
        return s


class Linter(Protocol):
    """All linters must implement this Protocol."""

    code: str
    name: str

    def check(self, file: Path, source: str) -> list[LintFinding]: ...

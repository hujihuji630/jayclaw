"""Base types for e2e verification checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    """Result of a single e2e check."""

    name: str
    status: CheckStatus
    message: str
    detail: str | None = None
    duration_ms: float = 0.0

    def render(self) -> str:
        icon = {"pass": "✓", "fail": "✗", "skip": "⊘"}[self.status.value]
        s = f"[{icon}] {self.name}: {self.message}"
        if self.detail:
            s += f"\n    {self.detail}"
        return s

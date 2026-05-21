"""Structured progress tracking for multi-step agent tasks."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Step:
    id: int
    description: str
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class Progress:
    goal: str
    steps: list[Step] = field(default_factory=list)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "in_progress"
    current_step: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def advance(self, step_id: int, new_status: str) -> None:
        """Update a step's status and timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        self.updated_at = now

        for step in self.steps:
            if step.id == step_id:
                step.status = new_status
                if new_status == "in_progress" and not step.started_at:
                    step.started_at = now
                    self.current_step = step_id
                elif new_status in ("completed", "skipped"):
                    step.completed_at = now
                break

        if all(s.status in ("completed", "skipped") for s in self.steps):
            self.status = "completed"
            self.completed_at = now

    def fail(self, reason: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.status = "failed"
        self.updated_at = now
        self.completed_at = now

    def save(self, workspace: Path) -> Path:
        """Write progress to .agents/progress.json."""
        agents_dir = workspace / ".agents"
        agents_dir.mkdir(exist_ok=True)
        path = agents_dir / "progress.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, workspace: Path) -> Progress | None:
        path = workspace / ".agents" / "progress.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        steps = [Step(**s) for s in data.pop("steps", [])]
        return cls(steps=steps, **data)

"""Task handoff document generation and detection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


HANDOFF_TEMPLATE = """# Task Handoff Document

**Generated**: {timestamp}
**Workspace**: {workspace}
**Reason**: Context utilization exceeded threshold ({ratio}%)

## 1. Original Goal

{goal}

## 2. What Has Been Done

{completed}

## 3. Current State

{state}

## 4. What Needs to Continue

{remaining}

## 5. Relevant Files

{files}

## 6. Key Decisions / Constraints

{decisions}

---

> To resume: start a new agent session in this workspace. The handoff doc will be auto-detected.
"""


@dataclass
class HandoffData:
    goal: str
    completed: list[str]
    state: str
    remaining: list[str]
    files: list[str]
    decisions: list[str]


def generate_handoff(
    data: HandoffData,
    workspace: Path,
    ratio: float,
) -> Path:
    """Write handoff document to .sessions/handoff_<timestamp>.md."""
    sessions_dir = workspace / ".sessions"
    sessions_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = sessions_dir / f"handoff_{ts}.md"

    content = HANDOFF_TEMPLATE.format(
        timestamp=datetime.now().isoformat(),
        workspace=str(workspace.resolve()),
        ratio=int(ratio * 100),
        goal=data.goal or "_(not specified)_",
        completed=_bullets(data.completed),
        state=data.state or "_(not specified)_",
        remaining=_bullets(data.remaining),
        files=_bullets(data.files),
        decisions=_bullets(data.decisions),
    )
    path.write_text(content, encoding="utf-8")
    return path


def _bullets(items: list[str]) -> str:
    if not items:
        return "_(none)_"
    return "\n".join(f"- {item}" for item in items)


def find_latest_handoff(workspace: Path) -> Path | None:
    """Find the most recent handoff_*.md in .sessions/."""
    sessions_dir = workspace / ".sessions"
    if not sessions_dir.exists():
        return None
    candidates = sorted(sessions_dir.glob("handoff_*.md"), reverse=True)
    return candidates[0] if candidates else None


def extract_handoff_data_from_history(
    messages: list[dict[str, Any]],
    progress_path: Path | None = None,
) -> HandoffData:
    """Best-effort extract handoff data from conversation history."""
    goal = ""
    completed: list[str] = []
    remaining: list[str] = []

    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            goal = msg["content"][:500]
            break

    if progress_path and progress_path.exists():
        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
            for step in data.get("steps", []):
                if step.get("status") == "completed":
                    completed.append(step["description"])
                elif step.get("status") in ("pending", "in_progress"):
                    remaining.append(step["description"])
        except (json.JSONDecodeError, KeyError):
            pass

    return HandoffData(
        goal=goal,
        completed=completed,
        state="_(see conversation history)_",
        remaining=remaining,
        files=[],
        decisions=[],
    )

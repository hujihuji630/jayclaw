"""Task handoff document generation and detection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


HANDOFF_DIR_NAME = "HANDOFFS"


HANDOFF_SYSTEM_PROMPT = """You are a senior engineering assistant writing a handoff document so that another agent (or the same agent in a fresh session) can resume the work without the previous conversation history.

Output a single Markdown document. Use the exact section headings shown in the template below. Be concrete, specific, and faithful to the conversation — do NOT invent files, decisions, or progress that the conversation does not support. If a section has no information, write `_(none)_`.

Required sections (in this order):

# Task Handoff Document

**Generated**: <ISO timestamp>
**Workspace**: <absolute workspace path>
**Reason**: Context utilization at <ratio>%

## 1. Original Goal
A faithful, self-contained restatement of what the user originally asked for. Include any constraints they specified.

## 2. What Has Been Done
A bulleted list of concrete actions already completed (files created/edited, commands run, decisions made). Each bullet should reference specifics (file paths, function names) when possible.

## 3. Current State
The current state of the workspace and conversation: what is working, what is partial, what was the last thing being worked on.

## 4. What Needs to Continue
A bulleted list of the next concrete steps. Order matters — start with what should be done first.

## 5. Relevant Files
A bulleted list of files that the next agent will need to read or modify, with a one-line note for each.

## 6. Key Decisions / Constraints
A bulleted list of architectural decisions, constraints, user preferences, or gotchas that the next agent must respect.

---

> To resume: open this file in the workspace and the agent will auto-detect it.

Rules:
- Do NOT include code blocks of long file contents — just reference the path.
- Do NOT add sections beyond those listed.
- Keep each bullet under two lines.
- Output Markdown only — no preamble, no closing remarks.
"""


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


def _handoff_dir(workspace: Path) -> Path:
    d = workspace / HANDOFF_DIR_NAME
    d.mkdir(exist_ok=True)
    return d


def _handoff_path(workspace: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _handoff_dir(workspace) / f"handoff_{ts}.md"


def generate_handoff(
    data: HandoffData,
    workspace: Path,
    ratio: float,
) -> Path:
    """Write template-based handoff document to HANDOFFS/handoff_<timestamp>.md."""
    path = _handoff_path(workspace)
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


async def generate_handoff_via_llm(
    llm: Any,
    messages: list[dict[str, Any]],
    workspace: Path,
    ratio: float,
    progress_path: Path | None = None,
) -> Path:
    """Generate handoff via LLM call, fall back to template on failure.

    On LLM failure the template fallback is rendered fully in memory and
    written exactly once, with a trailing HTML comment recording the original
    error — avoids the read-after-write race the previous implementation had.
    """
    from jay_llm.models import Message

    transcript = _format_transcript(messages)
    progress_summary = _format_progress(progress_path)

    user_prompt = f"""Generate a handoff document for the following session.

**Workspace**: {workspace.resolve()}
**Generated**: {datetime.now().isoformat()}
**Context utilization**: {int(ratio * 100)}%

## Progress tracker (if any)
{progress_summary}

## Scratchpad notes (if any)
{_format_scratchpad(workspace)}

## Conversation transcript
{transcript}
"""

    llm_messages = [
        Message(role="system", content=HANDOFF_SYSTEM_PROMPT),
        Message(role="user", content=user_prompt),
    ]

    try:
        response = await llm.achat(llm_messages, temperature=0.2)
        markdown = (response.content or "").strip()
    except Exception as exc:
        fallback_data = extract_handoff_data_from_history(messages, progress_path, workspace)
        fallback_md = HANDOFF_TEMPLATE.format(
            timestamp=datetime.now().isoformat(),
            workspace=str(workspace.resolve()),
            ratio=int(ratio * 100),
            goal=fallback_data.goal or "_(not specified)_",
            completed=_bullets(fallback_data.completed),
            state=fallback_data.state or "_(not specified)_",
            remaining=_bullets(fallback_data.remaining),
            files=_bullets(fallback_data.files),
            decisions=_bullets(fallback_data.decisions),
        )
        fallback_md += f"\n\n<!-- LLM handoff generation failed: {exc!r}; fell back to template. -->\n"
        path = _handoff_path(workspace)
        path.write_text(fallback_md, encoding="utf-8")
        return path

    if not markdown.lstrip().startswith("# "):
        markdown = "# Task Handoff Document\n\n" + markdown

    path = _handoff_path(workspace)
    path.write_text(markdown, encoding="utf-8")
    return path


def _format_transcript(messages: list[dict[str, Any]], max_chars: int = 24000) -> str:
    if not messages:
        return "_(empty)_"
    lines: list[str] = []
    for msg in messages:
        role = (msg.get("role") or "?").upper()
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"### {role}\n{content}\n")
    text = "\n".join(lines)
    if len(text) > max_chars:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        text = f"{head}\n\n... (transcript truncated for length) ...\n\n{tail}"
    return text


def _format_progress(progress_path: Path | None) -> str:
    if not progress_path or not progress_path.exists():
        return "_(no progress.json)_"
    try:
        data = json.loads(progress_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "_(progress.json unreadable)_"
    steps = data.get("steps", [])
    if not steps:
        return "_(no steps recorded)_"
    return "\n".join(
        f"- [{s.get('status', '?')}] {s.get('description', '')}" for s in steps
    )


def _format_scratchpad(workspace: Path) -> str:
    path = workspace / ".jayclaw" / "scratchpad.md"
    if not path.exists():
        return "_(no scratchpad)_"
    content = path.read_text(encoding="utf-8").strip()
    return content if content else "_(empty)_"


def _bullets(items: list[str]) -> str:
    if not items:
        return "_(none)_"
    return "\n".join(f"- {item}" for item in items)


def find_latest_handoff(workspace: Path) -> Path | None:
    """Find the most recent handoff_*.md, preferring HANDOFFS/ then legacy .sessions/."""
    for dir_name in (HANDOFF_DIR_NAME, ".sessions"):
        d = workspace / dir_name
        if not d.exists():
            continue
        candidates = sorted(d.glob("handoff_*.md"), reverse=True)
        if candidates:
            return candidates[0]
    return None


def extract_handoff_data_from_history(
    messages: list[dict[str, Any]],
    progress_path: Path | None = None,
    workspace: Path | None = None,
) -> HandoffData:
    """Best-effort extract handoff data from conversation history (template fallback)."""
    goal = ""
    completed: list[str] = []
    remaining: list[str] = []
    decisions: list[str] = []

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

    # Pull decisions and next_steps from scratchpad if available
    if workspace:
        scratchpad_path = workspace / ".jayclaw" / "scratchpad.md"
        if scratchpad_path.exists():
            from jay_agent_core.tools.handlers_scratchpad import _parse
            sections = _parse(scratchpad_path.read_text(encoding="utf-8"))
            decisions.extend(sections.get("decisions", []))
            if not remaining:
                remaining.extend(sections.get("next_steps", []))

    return HandoffData(
        goal=goal,
        completed=completed,
        state="_(see conversation history)_",
        remaining=remaining,
        files=[],
        decisions=decisions,
    )

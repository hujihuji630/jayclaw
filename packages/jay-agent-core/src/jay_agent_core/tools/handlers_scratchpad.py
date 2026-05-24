"""Scratchpad tool handler — persistent structured notes for long tasks."""

import asyncio
from pathlib import Path

from .base import ToolResult

SECTIONS = ("progress", "findings", "decisions", "next_steps")

HANDLERS: dict[str, object] = {}


def _register(name: str):
    def decorator(fn):
        HANDLERS[name] = fn
        return fn
    return decorator


def _scratchpad_path(workspace: Path) -> Path:
    return workspace / ".jayclaw" / "scratchpad.md"


def _parse(text: str) -> dict[str, list[str]]:
    """Parse scratchpad.md into section -> lines mapping."""
    result: dict[str, list[str]] = {s: [] for s in SECTIONS}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            key = stripped[3:].strip().lower().replace(" ", "_")
            current = key if key in result else None
        elif current and stripped:
            result[current].append(stripped)
    return result


def _render(data: dict[str, list[str]]) -> str:
    parts = []
    for section in SECTIONS:
        parts.append(f"## {section}")
        for line in data.get(section, []):
            parts.append(line if line.startswith("- ") else f"- {line}")
        parts.append("")
    return "\n".join(parts)


@_register("scratchpad")
async def handle_scratchpad(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Read/append/clear structured notes in .jayclaw/scratchpad.md."""
    action = (args.get("action") or "").strip()
    section = (args.get("section") or "").strip().lower().replace(" ", "_") or None
    content = (args.get("content") or "").strip()
    workspace = Path(meta.get("workspace", ".")) if meta else Path(".")

    if action not in ("read", "append", "clear"):
        return ToolResult(ok=False, error=f"Unknown action: {action}. Use read/append/clear.")

    if section and section not in SECTIONS:
        return ToolResult(ok=False, error=f"Unknown section: {section}. Valid: {SECTIONS}")

    path = _scratchpad_path(workspace)

    if action == "read":
        if not path.exists():
            return ToolResult(ok=True, data="(scratchpad is empty)")
        data = _parse(path.read_text(encoding="utf-8"))
        if section:
            lines = data.get(section, [])
            return ToolResult(ok=True, data="\n".join(lines) if lines else f"(no notes in {section})")
        return ToolResult(ok=True, data=path.read_text(encoding="utf-8"))

    if action == "append":
        if not content:
            return ToolResult(ok=False, error="'content' is required for append.")
        if not section:
            return ToolResult(ok=False, error="'section' is required for append.")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _parse(path.read_text(encoding="utf-8")) if path.exists() else {s: [] for s in SECTIONS}
        data[section].append(content)
        path.write_text(_render(data), encoding="utf-8")
        return ToolResult(ok=True, data={"status": "appended", "section": section})

    # action == "clear"
    if section:
        if not path.exists():
            return ToolResult(ok=True, data={"status": "already empty"})
        data = _parse(path.read_text(encoding="utf-8"))
        data[section] = []
        path.write_text(_render(data), encoding="utf-8")
    else:
        if path.exists():
            path.unlink()
    return ToolResult(ok=True, data={"status": "cleared", "section": section or "all"})

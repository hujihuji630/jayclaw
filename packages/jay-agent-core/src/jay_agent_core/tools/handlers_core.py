"""Core tool handlers for agent reasoning and planning."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .base import ToolResult
from .schemas import get_all_schemas

# Handler registry
HANDLERS: dict[str, Any] = {}


def _register(name: str):
    """Decorator to register a tool handler.

    Args:
        name: Tool name

    Returns:
        Decorator function
    """

    def decorator(fn):
        HANDLERS[name] = fn
        return fn

    return decorator


@_register("think")
async def handle_think(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle think tool - internal reasoning.

    Args:
        args: Tool arguments with 'thought' field
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with thinking status
    """
    thought = args.get("thought", "").strip()

    if not thought:
        return ToolResult(ok=False, error="Thought is required")

    # Just acknowledge the thought - it's recorded in the conversation
    return ToolResult(ok=True, data={"status": "ok", "thought_length": len(thought)})


@_register("plan")
async def handle_plan(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle plan tool - multi-step task planning.

    Args:
        args: Tool arguments with 'goal' and 'steps' fields
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with plan validation and summary
    """
    goal = args.get("goal", "").strip()
    steps = args.get("steps", [])

    # Validate inputs
    if not goal:
        return ToolResult(ok=False, error="Goal is required")

    if not steps or not isinstance(steps, list):
        return ToolResult(ok=False, error="Steps are required and must be a list")

    if len(steps) == 0:
        return ToolResult(ok=False, error="At least one step is required")

    # Validate each step
    for i, step in enumerate(steps):
        if not isinstance(step, str) or not step.strip():
            return ToolResult(ok=False, error=f"Step {i + 1} must be a non-empty string")

    # Return plan summary
    return ToolResult(
        ok=True,
        data={
            "status": "planned",
            "goal": goal,
            "steps": steps,
            "total_steps": len(steps),
        },
    )


@_register("discover_tools")
async def handle_discover_tools(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle discover_tools - find and activate tools by keyword."""
    query = (args.get("query") or "").strip().lower()

    from .schemas import CORE_TOOL_NAMES

    # Prefer registry_enhanced passed via meta (has all registered tools)
    registry = meta.get("registry_enhanced") if meta else None

    if registry and hasattr(registry, "_schemas"):
        # Use registry_enhanced directly - it has all tools including web tools
        all_tool_schemas = registry._schemas
        deferred_tools = {
            name: schema.get("function", {}).get("description", "").split("\n")[0]
            for name, schema in all_tool_schemas.items()
            if name not in CORE_TOOL_NAMES
        }
    else:
        # Fallback to get_all_schemas
        all_schemas = get_all_schemas()
        deferred_tools = {
            name: schema["function"]["description"].split("\n")[0]
            for name, schema in all_schemas.items()
            if name not in CORE_TOOL_NAMES
        }

    # If no query, return available tools
    if not query:
        return ToolResult(
            ok=True,
            data={
                "loaded": [],
                "available": deferred_tools,
                "hint": "Provide a keyword to search for tools (e.g., 'web', 'search', 'api')",
            },
        )

    # Match tools by keyword
    matched = {
        name: desc
        for name, desc in deferred_tools.items()
        if query in name.lower() or query in desc.lower()
    }

    if not matched:
        return ToolResult(
            ok=True,
            data={
                "loaded": [],
                "message": f"No tools matched '{query}'.",
                "available_categories": list(deferred_tools.keys()),
            },
        )

    # Return matched tools with activation list
    return ToolResult(
        ok=True,
        data={
            "loaded": [{"name": n, "description": d} for n, d in matched.items()],
            "_activate": list(matched.keys()),
        },
    )


@_register("get_current_time")
async def handle_get_current_time(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle get_current_time - get current date and time with timezone.

    Args:
        args: Tool arguments with optional 'timezone' field
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with ISO 8601 formatted datetime
    """
    timezone_name = (args.get("timezone") or "UTC").strip()

    try:
        # Parse timezone
        if timezone_name.upper() == "UTC":
            tz = timezone.utc
            now = datetime.now(tz)
        else:
            tz_info = ZoneInfo(timezone_name)
            now = datetime.now(tz_info)

        # Format as ISO 8601
        iso_time = now.isoformat()

        return ToolResult(
            ok=True,
            data={
                "datetime": iso_time,
                "timezone": timezone_name,
                "timestamp": int(now.timestamp()),
            },
        )
    except Exception as e:
        return ToolResult(
            ok=False,
            error=f"Invalid timezone '{timezone_name}': {e}",
        )


@_register("read_knowledge")
async def handle_read_knowledge(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Load a knowledge document from docs/agent-knowledge/."""
    topic = (args.get("topic") or "").strip().lower()

    if not topic:
        return ToolResult(ok=False, error="topic is required")

    workspace = Path(meta.get("workspace", ".")) if meta else Path(".")
    knowledge_dir = workspace / "docs" / "agent-knowledge"

    if "/" in topic or "\\" in topic or ".." in topic:
        return ToolResult(ok=False, error=f"Invalid topic: {topic}")

    doc_path = knowledge_dir / f"{topic}.md"

    if not doc_path.exists():
        available = sorted(
            p.stem for p in knowledge_dir.glob("*.md") if p.is_file()
        ) if knowledge_dir.exists() else []
        return ToolResult(
            ok=False,
            error=f"Topic '{topic}' not found. Available: {available}",
        )

    content = doc_path.read_text(encoding="utf-8")
    return ToolResult(ok=True, data={"topic": topic, "content": content})


@_register("update_progress")
async def handle_update_progress(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle update_progress - structured task progress tracking."""
    from ..progress import Progress, Step

    action = (args.get("action") or "").strip()
    workspace = Path(meta.get("workspace", ".")) if meta else Path(".")

    if action == "init":
        goal = args.get("goal", "").strip()
        steps_raw = args.get("steps", [])
        if not goal or not steps_raw:
            return ToolResult(ok=False, error="'goal' and 'steps' required for init")
        steps = [Step(id=i + 1, description=s) for i, s in enumerate(steps_raw)]
        progress = Progress(goal=goal, steps=steps)
        progress.save(workspace)
        return ToolResult(ok=True, data={"task_id": progress.task_id, "total_steps": len(steps)})

    elif action == "advance":
        step_id = args.get("step_id")
        step_status = args.get("step_status", "completed")
        if step_id is None:
            return ToolResult(ok=False, error="'step_id' required for advance")
        progress = Progress.load(workspace)
        if not progress:
            return ToolResult(ok=False, error="No active progress. Call init first.")
        progress.advance(int(step_id), step_status)
        progress.save(workspace)
        return ToolResult(ok=True, data={"step_id": step_id, "status": progress.status})

    elif action == "fail":
        progress = Progress.load(workspace)
        if not progress:
            return ToolResult(ok=False, error="No active progress.")
        progress.fail()
        progress.save(workspace)
        return ToolResult(ok=True, data={"status": "failed"})

    else:
        return ToolResult(ok=False, error=f"Unknown action: {action}")

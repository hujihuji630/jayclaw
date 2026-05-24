"""Delegate tool handler — spawn isolated sub-agent for research tasks."""

import asyncio
from pathlib import Path
from typing import Any

from .base import ToolResult

MAX_CHILD_ITERATIONS = 5
DEFAULT_SUMMARY_TOKENS = 1500

HANDLERS: dict[str, object] = {}


def _register(name: str):
    def decorator(fn):
        HANDLERS[name] = fn
        return fn
    return decorator


@_register("delegate")
async def handle_delegate(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Spawn an isolated sub-agent for research/analysis tasks.

    The sub-agent gets its own context window with read-only tools,
    runs up to MAX_CHILD_ITERATIONS, and returns a compressed summary.
    """
    task = (args.get("task") or "").strip()
    if not task:
        return ToolResult(ok=False, error="'task' is required.")

    max_tokens = int(args.get("max_tokens", DEFAULT_SUMMARY_TOKENS))
    llm = meta.get("llm")
    if not llm:
        return ToolResult(ok=False, error="LLM not available for delegation.")

    workspace = Path(meta.get("workspace", "."))
    child_tools: list[dict[str, Any]] = meta.get("child_tools", [])

    from ..agent import Agent

    child = Agent(
        name="ResearchAgent",
        llm=llm,
        system_prompt=(
            "You are a focused research assistant. Complete the task concisely. "
            "Report key facts, file paths, and conclusions. No preamble."
        ),
        max_rounds=MAX_CHILD_ITERATIONS,
    )

    for tool_spec in child_tools:
        child.registry_enhanced.register(**tool_spec)

    try:
        response = await child.arun(task)
        content = response.content or ""
    except Exception as e:
        return ToolResult(ok=False, error=f"Sub-agent failed: {e}")

    summary = await _compress_if_needed(content, max_tokens, llm)
    return ToolResult(ok=True, data=summary)


async def _compress_if_needed(content: str, max_tokens: int, llm: Any) -> str:
    """Compress content via LLM if it exceeds the token budget."""
    from ..token_counter import count_tokens

    if not content or count_tokens(content) <= max_tokens:
        return content

    from jay_llm import Message

    try:
        resp = await llm.achat(
            [Message(role="user", content=f"Compress to key facts, file paths, and conclusions:\n\n{content}")],
            max_tokens=max_tokens,
        )
        return resp.content or content
    except Exception:
        # Fallback: hard truncate
        ratio = max_tokens / max(count_tokens(content), 1)
        cut = int(len(content) * ratio * 0.9)
        return content[:cut] + "\n[... truncated]"

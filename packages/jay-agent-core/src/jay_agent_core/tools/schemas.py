"""Tool schemas and configuration for core agent tools."""

from typing import Any


def _fn(
    name: str,
    desc: str,
    params: dict[str, Any],
    *,
    strict: bool = True,
    permission: str | None = None,
) -> dict[str, Any]:
    """Build an OpenAI function-calling tool schema.

    Args:
        name: Tool name
        desc: Tool description
        params: Parameter schema
        strict: Whether to use strict mode
        permission: Permission level (none/read/storage/write)

    Returns:
        OpenAI function calling schema
    """
    if permission is None:
        raise ValueError(f"Missing permission for tool {name}")

    valid_permissions = {"none", "read", "storage", "write"}
    if permission not in valid_permissions:
        raise ValueError(f"Invalid permission {permission!r} for tool {name}")

    params.setdefault("additionalProperties", False)

    return {
        "type": "function",
        "_permission": permission,  # Internal metadata, stripped before sending to LLM
        "function": {
            "name": name,
            "strict": strict,
            "description": desc,
            "parameters": {
                "type": "object",
                **params,
            },
        },
    }


# ---------------------------------------------------------------------------
# Core tool names (always loaded)
# ---------------------------------------------------------------------------

CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "think",
        "plan",
        "discover_tools",
        "get_current_time",
        "read_knowledge",
        "update_progress",
        "scratchpad",
        "delegate",
    }
)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "think",
        "Use this tool for quick internal reasoning about a specific decision or action. "
        "Your thought is recorded and visible to you in subsequent turns.",
        {
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Your reasoning about a specific decision",
                }
            },
            "required": ["thought"],
        },
        permission="none",
    ),
    _fn(
        "plan",
        "Create an execution plan for multi-step tasks. "
        "Call this BEFORE executing any request that needs 3+ tool calls "
        "(research, multi-platform analysis, content campaigns). "
        "List your steps clearly, then execute them in order.",
        {
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "What you are trying to accomplish",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of execution steps",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                },
            },
            "required": ["goal", "steps"],
        },
        permission="none",
    ),
    _fn(
        "discover_tools",
        "Load additional tools by keyword. Core tools (think, plan) are always available. "
        "Call this to unlock specialized tools.\n"
        "Example inputs:\n"
        '- {"query": "web"} — loads web search and read tools\n'
        '- {"query": "search"} — loads search-related tools',
        {
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search for tools (e.g., 'web', 'search', 'api')",
                }
            },
            "required": ["query"],
        },
        permission="none",
    ),
    _fn(
        "get_current_time",
        "Get the current date and time in ISO 8601 format with timezone. "
        "Use this when you need to know the current time for scheduling, "
        "time-sensitive operations, or timestamping.",
        {
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "Timezone name (e.g., 'UTC', 'America/New_York'). Defaults to UTC."
                    ),
                }
            },
            "required": [],
        },
        permission="none",
    ),
    _fn(
        "read_knowledge",
        "Load a knowledge document by topic ID. "
        "Use this when you need detailed information about a specific mechanism. "
        "Available topics are listed in the Knowledge Map section of AGENTS.md.",
        {
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "Topic ID from Knowledge Map (e.g., 'tool-lazy-loading', "
                        "'resilience-chain', 'ssrf-protection')"
                    ),
                }
            },
            "required": ["topic"],
        },
        permission="read",
    ),
    _fn(
        "update_progress",
        "Update task progress. Call this to initialize a plan or mark steps as completed. "
        "External tools (IDE, Web UI) read .jayclaw/progress.json to display progress.",
        {
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["init", "advance", "fail"],
                    "description": "Action: init (create plan), advance (update step), fail (mark failed)",
                },
                "goal": {
                    "type": "string",
                    "description": "Task goal (required for init)",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Step descriptions (required for init)",
                },
                "step_id": {
                    "type": "integer",
                    "description": "Step ID to update (required for advance)",
                },
                "step_status": {
                    "type": "string",
                    "enum": ["in_progress", "completed", "skipped"],
                    "description": "New status for the step (required for advance)",
                },
            },
            "required": ["action"],
        },
        permission="storage",
    ),
    _fn(
        "scratchpad",
        "Persistent structured notes for long tasks. Write key findings, decisions, "
        "and next steps so they survive context resets. Notes are stored in "
        ".jayclaw/scratchpad.md and auto-loaded in new sessions.",
        {
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "append", "clear"],
                    "description": "Action: read (view notes), append (add note), clear (reset)",
                },
                "section": {
                    "type": "string",
                    "enum": ["progress", "findings", "decisions", "next_steps"],
                    "description": "Section to operate on. Omit to read/clear all.",
                },
                "content": {
                    "type": "string",
                    "description": "Note content (required for append)",
                },
            },
            "required": ["action"],
        },
        permission="storage",
    ),
    _fn(
        "delegate",
        "Delegate a research or analysis task to a sub-agent with its own isolated context. "
        "The sub-agent has read-only file tools, runs independently, and returns a compressed "
        "summary. USE WHEN: searching 3+ files, exploring unfamiliar code areas, broad pattern "
        "finding, or any task where exploration would consume significant context. "
        "DO NOT USE for simple single-file reads or tasks requiring file writes.",
        {
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Clear description of what to research or analyze",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum tokens for the returned summary (default 1500)",
                },
            },
            "required": ["task"],
        },
        permission="read",
    ),
]


# ---------------------------------------------------------------------------
# Tool permissions mapping
# ---------------------------------------------------------------------------

TOOL_PERMISSIONS: dict[str, str] = {
    schema["function"]["name"]: schema["_permission"] for schema in TOOL_SCHEMAS
}


# ---------------------------------------------------------------------------
# Tool budgets (timeout and retry configuration)
# ---------------------------------------------------------------------------

TOOL_BUDGETS: dict[str, dict[str, int]] = {
    "think": {"timeout": 1, "max_retries": 0},
    "plan": {"timeout": 2, "max_retries": 0},
    "discover_tools": {"timeout": 1, "max_retries": 0},
    "get_current_time": {"timeout": 1, "max_retries": 0},
    "read_knowledge": {"timeout": 5, "max_retries": 1},
    "update_progress": {"timeout": 2, "max_retries": 0},
    "scratchpad": {"timeout": 2, "max_retries": 0},
    "delegate": {"timeout": 120, "max_retries": 0},
}


# ---------------------------------------------------------------------------
# Deferred tool index (keyword-based tool discovery)
# ---------------------------------------------------------------------------

DEFERRED_TOOL_INDEX: dict[str, list[str]] = {
    "web": ["search_web", "read_webpage"],
    "search": ["search_web", "search_x", "search_reddit"],
    "read": ["read_webpage", "read_file"],
    "browser": ["open_browser", "click_element", "screenshot"],
    "api": ["make_api_call", "parse_json"],
    "file": ["read_file", "write_file", "list_files"],
    "code": ["run_code", "analyze_code", "format_code"],
    "social": ["post_x", "post_reddit", "get_x_profile"],
}


# ---------------------------------------------------------------------------
# Parallel-safe tools (can execute concurrently)
# ---------------------------------------------------------------------------

PARALLEL_SAFE_TOOLS: frozenset[str] = frozenset(
    {
        # Core tools
        "think",
        "get_current_time",
        "discover_tools",
        "read_knowledge",
        "scratchpad",
        "delegate",
        # Read-only tools (safe to run in parallel)
        "search_web",
        "read_webpage",
        "read_file",
        "list_files",
        "search_x",
        "search_reddit",
        "get_x_profile",
        "get_reddit_post",
        "analyze_code",
        # Note: write tools (write_file, post_x, etc.) are NOT in this set
        # and will be executed sequentially
    }
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def strip_internal_fields(schemas: list[dict]) -> list[dict]:
    """Remove internal metadata fields from schemas before sending to LLM.

    Args:
        schemas: List of tool schemas

    Returns:
        Schemas with internal fields removed
    """
    return [{k: v for k, v in s.items() if not k.startswith("_")} for s in schemas]


def get_core_schemas() -> list[dict]:
    """Get schemas for core tools only.

    Returns:
        List of core tool schemas (stripped of internal fields)
    """
    core_schemas = [s for s in TOOL_SCHEMAS if s["function"]["name"] in CORE_TOOL_NAMES]
    return strip_internal_fields(core_schemas)


def get_all_schemas() -> dict[str, dict]:
    """Get all tool schemas as a name-to-schema mapping.

    This includes both core tools and any tools registered in the global registry.

    Returns:
        Dictionary mapping tool names to schemas (stripped of internal fields)
    """
    from . import _global_registry

    # Start with core tools
    stripped = strip_internal_fields(TOOL_SCHEMAS)
    result = {s["function"]["name"]: s for s in stripped}

    # Add tools from global registry
    if _global_registry and hasattr(_global_registry, '_schemas'):
        for name, schema in _global_registry._schemas.items():
            if name not in result:
                # Strip internal fields from registry schemas
                clean_schema = {k: v for k, v in schema.items() if not k.startswith("_")}
                result[name] = clean_schema

    return result

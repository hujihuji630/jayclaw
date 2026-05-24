"""Resolve short, human-readable labels for tools from registry schemas.

Background: the web UI's SSE status messages used to embed a hardcoded
Chinese label table (``_TOOL_LABELS = {"run_command": "执行命令", ...}``).
That table:

* Had to be updated by hand whenever a new tool was added — the tool would
  silently show up as ``调用 <name>...`` because nobody remembered to extend
  the dict.
* Was a one-off, English-incompatible place to localize tool names.

Now labels are derived from the tool's ``schema["function"]["description"]``
which every tool already has (it's what the LLM reads). We take its first
short clause so it fits a status line. Per-locale overrides can be added
later via the ``_OVERRIDES`` table without touching ``server.py``.
"""

from __future__ import annotations

import re
from typing import Any

# Optional fixed overrides — kept here so adding a translation for a specific
# tool is a single-line edit. New tools NOT in this table still render
# automatically from their schema description. This is the only place labels
# need to be touched.
_OVERRIDES: dict[str, str] = {
    "run_command": "执行命令",
    "search_web": "搜索网络",
    "read_webpage": "读取网页",
    "read_file": "读取文件",
    "write_file": "写入文件",
    "list_files": "列出文件",
    "grep_files": "搜索文件内容",
    "find_files": "查找文件",
    "generate_code": "生成代码",
    "explain_code": "分析代码",
    "think": "深度思考",
    "plan": "制定计划",
    "git_status": "查看 Git 状态",
    "git_diff": "查看代码差异",
    "git_commit": "提交代码",
    "search_zhihu": "搜索知乎",
    "translate_to_english": "翻译内容",
    "discover_tools": "加载工具",
    "get_current_time": "获取时间",
}

_MAX_LABEL_CHARS = 24


def _first_clause(description: str) -> str:
    """Return the first clause of a tool description, trimmed for status display.

    Splits on Chinese / English sentence-end punctuation and takes the first
    non-empty chunk. Falls back to the raw description if no punctuation found.
    """
    if not description:
        return ""
    # Split on the first sentence-end or comma-equivalent
    parts = re.split(r"[。.！!；;\n]", description, maxsplit=1)
    first = parts[0].strip()
    if len(first) > _MAX_LABEL_CHARS:
        first = first[: _MAX_LABEL_CHARS - 1].rstrip() + "…"
    return first


def build_tool_label_map(schemas: list[dict[str, Any]]) -> dict[str, str]:
    """Build a {tool_name: display_label} map from a list of OpenAI tool schemas.

    Resolution order, per tool:
    1. ``_OVERRIDES[name]`` if present (curated localized labels)
    2. First-clause of ``schema["function"]["description"]``
    3. The tool name itself (raw fallback)

    Args:
        schemas: OpenAI function-calling schemas as returned by
            ``registry.get_schemas()``.

    Returns:
        Mapping that ``server.py``'s on_tool_start/on_tool_end can look up
        in O(1).
    """
    labels: dict[str, str] = {}
    for entry in schemas or []:
        fn = entry.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        if name in _OVERRIDES:
            labels[name] = _OVERRIDES[name]
            continue
        desc = fn.get("description") or ""
        candidate = _first_clause(desc)
        labels[name] = candidate or name
    return labels


def resolve_label(labels: dict[str, str], tool_name: str) -> str:
    """Lookup a label with a sensible fallback.

    ``labels`` is the map returned by ``build_tool_label_map``; passing an
    unknown tool name returns the override if any, else the name itself.
    Never returns an empty string.
    """
    if not tool_name:
        return ""
    if tool_name in labels:
        return labels[tool_name]
    if tool_name in _OVERRIDES:
        return _OVERRIDES[tool_name]
    return tool_name

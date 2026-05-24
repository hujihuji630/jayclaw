"""Tests for jay_web_ui.tool_labels — schema-driven display labels.

Pins behaviour:
- Known tool names use the curated _OVERRIDES table
- Unknown tools fall back to the first clause of their schema description
- Unknown tools with no schema fall back to the tool name itself
- Long descriptions are clipped at _MAX_LABEL_CHARS
"""

from __future__ import annotations

from jay_web_ui.tool_labels import (
    _MAX_LABEL_CHARS,
    _OVERRIDES,
    build_tool_label_map,
    resolve_label,
)


def _schema(name: str, description: str) -> dict:
    """Tiny helper to mint an OpenAI-style function schema for tests."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }


# ---------------------------------------------------------------------------
# build_tool_label_map
# ---------------------------------------------------------------------------


def test_known_tools_get_override_label():
    schemas = [_schema("run_command", "Execute a shell command on the host system.")]
    labels = build_tool_label_map(schemas)
    # Override wins over schema-derived description
    assert labels["run_command"] == _OVERRIDES["run_command"]
    assert labels["run_command"] == "执行命令"


def test_unknown_tool_uses_schema_description_first_clause():
    schemas = [_schema(
        "my_custom_tool",
        "Render a tarot card. Returns the image as base64.",
    )]
    labels = build_tool_label_map(schemas)
    # First sentence only, no period
    assert labels["my_custom_tool"] == "Render a tarot card"


def test_unknown_tool_chinese_punctuation_split():
    schemas = [_schema(
        "summarize_pdf",
        "分析 PDF 文件内容。返回字符级摘要。需要 LLM 可用。",
    )]
    labels = build_tool_label_map(schemas)
    assert labels["summarize_pdf"] == "分析 PDF 文件内容"


def test_unknown_tool_no_punctuation_clipped():
    """Long descriptions without sentence-end punctuation get truncated."""
    long_desc = "x" * 100
    schemas = [_schema("bigdescr_tool", long_desc)]
    labels = build_tool_label_map(schemas)
    label = labels["bigdescr_tool"]
    # Truncated with an ellipsis sentinel
    assert len(label) <= _MAX_LABEL_CHARS
    assert label.endswith("…")


def test_empty_description_falls_back_to_name():
    schemas = [_schema("nobody_documented_me", "")]
    labels = build_tool_label_map(schemas)
    assert labels["nobody_documented_me"] == "nobody_documented_me"


def test_schema_missing_function_key_is_skipped():
    schemas = [
        {"type": "function"},  # no "function" key
        _schema("valid_tool", "Does a thing."),
    ]
    labels = build_tool_label_map(schemas)
    # Bad entry didn't crash; valid one made it
    assert "valid_tool" in labels
    assert labels["valid_tool"] == "Does a thing"


def test_schema_missing_name_is_skipped():
    schemas = [
        {"type": "function", "function": {"description": "no name here"}},
        _schema("ok", "ok desc."),
    ]
    labels = build_tool_label_map(schemas)
    assert list(labels) == ["ok"]


def test_empty_schemas_returns_empty_map():
    assert build_tool_label_map([]) == {}
    assert build_tool_label_map(None) == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_label
# ---------------------------------------------------------------------------


def test_resolve_label_uses_provided_map():
    labels = {"foo": "Frobnicate"}
    assert resolve_label(labels, "foo") == "Frobnicate"


def test_resolve_label_falls_back_to_overrides_when_map_missing_tool():
    """Even when the per-session map doesn't have a tool (e.g. discovered late),
    the global override table is the second-chance lookup."""
    labels: dict[str, str] = {}
    assert resolve_label(labels, "run_command") == "执行命令"


def test_resolve_label_falls_back_to_raw_name():
    """No map entry, no override → return the name verbatim, never empty."""
    labels: dict[str, str] = {}
    assert resolve_label(labels, "totally_new_tool") == "totally_new_tool"


def test_resolve_label_empty_tool_name_returns_empty():
    """Belt-and-braces — never return None / blow up on bad input."""
    assert resolve_label({"x": "y"}, "") == ""


def test_new_tool_auto_visible_in_status_line():
    """End-to-end: a brand-new tool added to the registry shows up in the
    label map without anyone touching tool_labels.py."""
    schemas = [_schema(
        "freshly_added_tool",
        "Generate a sonnet about Kubernetes.",
    )]
    labels = build_tool_label_map(schemas)
    # ⚙ {label}... in the SSE status string would be "⚙ Generate a sonnet about Kub… ..."
    label = resolve_label(labels, "freshly_added_tool")
    assert label  # non-empty — the regression we're guarding against
    assert "freshly_added_tool" != label  # not just the raw name

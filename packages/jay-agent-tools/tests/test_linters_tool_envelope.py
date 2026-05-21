"""Tests for ToolEnvelopeLinter (JC002)."""

from pathlib import Path

from jay_agent_tools.linters.tool_envelope import ToolEnvelopeLinter


def test_detects_dict_return_in_tool_handler():
    src = """
@tool
def my_handler():
    return {"ok": True, "data": 1}
"""
    findings = ToolEnvelopeLinter().check(Path("h.py"), src)
    assert any(f.code == "JC002" for f in findings)
    assert findings[0].suggestion


def test_accepts_toolresult_return():
    src = """
@tool
def my_handler():
    return ToolResult(ok=True, data=1)
"""
    assert ToolEnvelopeLinter().check(Path("h.py"), src) == []


def test_ignores_non_tool_functions():
    src = """
def helper():
    return {"ok": True}
"""
    assert ToolEnvelopeLinter().check(Path("h.py"), src) == []


def test_detects_string_literal_return():
    src = """
@_register("foo")
async def handle_foo(args, user_id, meta, cancel=None):
    return "raw string"
"""
    findings = ToolEnvelopeLinter().check(Path("h.py"), src)
    assert any(f.code == "JC002" for f in findings)


def test_suggestion_non_empty():
    src = """
@tool
def my_handler():
    return [1, 2, 3]
"""
    findings = ToolEnvelopeLinter().check(Path("h.py"), src)
    for f in findings:
        assert f.suggestion.strip()

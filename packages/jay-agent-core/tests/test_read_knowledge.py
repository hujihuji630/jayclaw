"""Tests for read_knowledge tool handler."""

import asyncio
from pathlib import Path

import pytest

from jay_agent_core.tools.handlers_core import handle_read_knowledge


@pytest.fixture
def knowledge_dir(tmp_path):
    """Create a temporary knowledge directory with sample docs."""
    docs = tmp_path / "docs" / "agent-knowledge"
    docs.mkdir(parents=True)
    (docs / "tool-lazy-loading.md").write_text("# Tool Lazy Loading\n\nContent here.", encoding="utf-8")
    (docs / "resilience-chain.md").write_text("# Resilience Chain\n\nContent here.", encoding="utf-8")
    return tmp_path


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_read_existing_topic(knowledge_dir):
    result = _run(handle_read_knowledge(
        {"topic": "tool-lazy-loading"}, "test", {"workspace": str(knowledge_dir)}, None
    ))
    assert result.ok is True
    assert "Tool Lazy Loading" in result.data["content"]


def test_read_missing_topic(knowledge_dir):
    result = _run(handle_read_knowledge(
        {"topic": "nonexistent"}, "test", {"workspace": str(knowledge_dir)}, None
    ))
    assert result.ok is False
    assert "not found" in result.error


def test_empty_topic(knowledge_dir):
    result = _run(handle_read_knowledge(
        {"topic": ""}, "test", {"workspace": str(knowledge_dir)}, None
    ))
    assert result.ok is False
    assert "required" in result.error


def test_path_traversal_blocked(knowledge_dir):
    result = _run(handle_read_knowledge(
        {"topic": "../../../etc/passwd"}, "test", {"workspace": str(knowledge_dir)}, None
    ))
    assert result.ok is False
    assert "Invalid" in result.error


def test_lists_available_topics(knowledge_dir):
    result = _run(handle_read_knowledge(
        {"topic": "wrong"}, "test", {"workspace": str(knowledge_dir)}, None
    ))
    assert result.ok is False
    assert "tool-lazy-loading" in result.error

"""Tests for http_check."""

import asyncio

import pytest

from jay_agent_tools.e2e.http_check import http_check


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_http_check_unreachable():
    result = _run(http_check("http://127.0.0.1:19999/nonexistent", timeout=1.0))
    assert result.status.value == "fail"
    assert "Request failed" in result.message


def test_http_check_render():
    result = _run(http_check("http://127.0.0.1:19999/x", timeout=0.5))
    rendered = result.render()
    assert "✗" in rendered or "⊘" in rendered


def test_http_check_result_structure():
    result = _run(http_check("http://127.0.0.1:19999/x", timeout=0.5))
    assert result.name.startswith("http:")
    assert result.duration_ms >= 0

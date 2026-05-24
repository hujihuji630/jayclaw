"""Tests for AnthropicProvider.astream tool_calls accumulation.

The provider buffers Anthropic's content_block_start / content_block_delta
stream events for ``tool_use`` blocks, then emits a final StreamChunk with
OpenAI-style ``tool_calls``. This test pins that contract using fake events.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# Skip the whole file if the anthropic SDK isn't installed; the provider module
# imports it at top level.
pytest.importorskip("anthropic")

from jay_llm.config import Config  # noqa: E402
from jay_llm.models import Message  # noqa: E402
from jay_llm.providers.anthropic import AnthropicProvider  # noqa: E402


def _make_event(type_, **kwargs):
    """Build an Anthropic-SDK-shaped streaming event using SimpleNamespace."""
    return SimpleNamespace(type=type_, **kwargs)


class _FakeStream:
    """Minimal async-context-manager mimicking ``messages.stream(...)`` output."""

    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        async def gen():
            for ev in self._events:
                yield ev
        return gen()


def _build_provider(events):
    cfg = Config(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-test",
    )
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.config = cfg
    provider.client = MagicMock()
    provider.async_client = MagicMock()
    provider.async_client.messages = MagicMock()
    provider.async_client.messages.stream = MagicMock(return_value=_FakeStream(events))
    return provider


def test_astream_yields_text_only_when_no_tool_use():
    """Plain text streams produce text chunks and no final tool_calls chunk."""
    events = [
        _make_event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="Hello"),
        ),
        _make_event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text=" world"),
        ),
    ]
    provider = _build_provider(events)

    async def collect():
        out = []
        async for chunk in provider.astream(
            [Message(role="user", content="hi")],
            model="claude-3-5-sonnet-20241022",
        ):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    assert [c.content for c in chunks] == ["Hello", " world"]
    assert all(c.tool_calls is None for c in chunks)


def test_astream_accumulates_tool_use_into_final_chunk():
    """tool_use blocks accumulate input_json_delta and emit one final chunk."""
    events = [
        _make_event(
            "content_block_start",
            index=0,
            content_block=SimpleNamespace(
                type="tool_use",
                id="toolu_abc",
                name="run_command",
                input={},
            ),
        ),
        _make_event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"cmd"'),
        ),
        _make_event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json=': "ls"}'),
        ),
    ]
    provider = _build_provider(events)

    async def collect():
        out = []
        async for chunk in provider.astream(
            [Message(role="user", content="run ls")],
            model="claude-3-5-sonnet-20241022",
        ):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    # No text chunks emitted; one final chunk with tool_calls.
    assert len(chunks) == 1
    final = chunks[0]
    assert final.finish_reason == "tool_calls"
    assert final.tool_calls is not None
    assert len(final.tool_calls) == 1
    tc = final.tool_calls[0]
    assert tc["id"] == "toolu_abc"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "run_command"
    assert tc["function"]["arguments"] == '{"cmd": "ls"}'


def test_astream_text_and_tool_use_interleaved():
    """Common shape: model writes some text, then decides to call a tool."""
    events = [
        _make_event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="Let me check. "),
        ),
        _make_event(
            "content_block_start",
            index=1,
            content_block=SimpleNamespace(
                type="tool_use",
                id="toolu_1",
                name="search_web",
                input={},
            ),
        ),
        _make_event(
            "content_block_delta",
            index=1,
            delta=SimpleNamespace(
                type="input_json_delta",
                partial_json='{"query": "weather"}',
            ),
        ),
    ]
    provider = _build_provider(events)

    async def collect():
        out = []
        async for chunk in provider.astream(
            [Message(role="user", content="weather?")],
            model="claude-3-5-sonnet-20241022",
        ):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    assert chunks[0].content == "Let me check. "
    assert chunks[-1].finish_reason == "tool_calls"
    assert chunks[-1].tool_calls[0]["function"]["name"] == "search_web"


def test_astream_tool_use_with_empty_input_falls_back_to_empty_object():
    """If the model emits no input_json_delta, we still send valid JSON `{}`."""
    events = [
        _make_event(
            "content_block_start",
            index=0,
            content_block=SimpleNamespace(
                type="tool_use",
                id="toolu_empty",
                name="get_current_time",
                input={},
            ),
        ),
        # No input_json_delta events — the tool takes no args.
    ]
    provider = _build_provider(events)

    async def collect():
        return [c async for c in provider.astream(
            [Message(role="user", content="time?")],
            model="claude-3-5-sonnet-20241022",
        )]

    chunks = asyncio.run(collect())
    assert len(chunks) == 1
    tc = chunks[0].tool_calls[0]
    assert tc["function"]["name"] == "get_current_time"
    assert tc["function"]["arguments"] == "{}"


def test_astream_multiple_tool_use_blocks():
    """Two parallel tool calls in one response — both make it into tool_calls."""
    events = [
        _make_event(
            "content_block_start",
            index=0,
            content_block=SimpleNamespace(
                type="tool_use", id="toolu_a", name="read_file", input={},
            ),
        ),
        _make_event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(
                type="input_json_delta", partial_json='{"path": "a.txt"}',
            ),
        ),
        _make_event(
            "content_block_start",
            index=1,
            content_block=SimpleNamespace(
                type="tool_use", id="toolu_b", name="read_file", input={},
            ),
        ),
        _make_event(
            "content_block_delta",
            index=1,
            delta=SimpleNamespace(
                type="input_json_delta", partial_json='{"path": "b.txt"}',
            ),
        ),
    ]
    provider = _build_provider(events)

    async def collect():
        return [c async for c in provider.astream(
            [Message(role="user", content="read both")],
            model="claude-3-5-sonnet-20241022",
        )]

    chunks = asyncio.run(collect())
    final = chunks[-1]
    assert len(final.tool_calls) == 2
    names_args = {(tc["id"], tc["function"]["arguments"]) for tc in final.tool_calls}
    assert ("toolu_a", '{"path": "a.txt"}') in names_args
    assert ("toolu_b", '{"path": "b.txt"}') in names_args

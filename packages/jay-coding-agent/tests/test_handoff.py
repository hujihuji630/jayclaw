"""Tests for jay_coding_agent.handoff — handoff document generation.

Covers:
- Template-based generate_handoff()
- LLM-driven generate_handoff_via_llm() success path
- LLM failure → template fallback (single-write contract)
- find_latest_handoff() preferring HANDOFFS/ over .sessions/
- extract_handoff_data_from_history() with and without progress.json
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from jay_coding_agent.handoff import (
    HANDOFF_DIR_NAME,
    HandoffData,
    extract_handoff_data_from_history,
    find_latest_handoff,
    generate_handoff,
    generate_handoff_via_llm,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# generate_handoff (template-based)
# ---------------------------------------------------------------------------


def test_generate_handoff_writes_all_six_sections(tmp_path: Path):
    data = HandoffData(
        goal="rewrite the auth flow",
        completed=["read auth.py", "drafted plan in PLAN.md"],
        state="auth/login_handler.py is half-rewritten",
        remaining=["finish login_handler", "add tests"],
        files=["auth/login_handler.py", "tests/test_auth.py"],
        decisions=["use jwt instead of sessions"],
    )
    path = generate_handoff(data, tmp_path, ratio=0.42)

    assert path.parent == tmp_path / HANDOFF_DIR_NAME
    assert path.name.startswith("handoff_") and path.name.endswith(".md")
    text = path.read_text(encoding="utf-8")

    for heading in (
        "## 1. Original Goal",
        "## 2. What Has Been Done",
        "## 3. Current State",
        "## 4. What Needs to Continue",
        "## 5. Relevant Files",
        "## 6. Key Decisions / Constraints",
    ):
        assert heading in text

    # Ratio surfaces as integer percent
    assert "(42%)" in text
    # Bulleted items render
    assert "- read auth.py" in text
    assert "- finish login_handler" in text
    # Decisions
    assert "- use jwt instead of sessions" in text


def test_generate_handoff_empty_lists_render_as_none(tmp_path: Path):
    data = HandoffData(
        goal="",
        completed=[],
        state="",
        remaining=[],
        files=[],
        decisions=[],
    )
    path = generate_handoff(data, tmp_path, ratio=0.0)
    text = path.read_text(encoding="utf-8")
    # _bullets([]) returns "_(none)_"
    assert "_(none)_" in text
    # Empty goal/state render as "_(not specified)_"
    assert "_(not specified)_" in text


def test_generate_handoff_creates_handoff_dir(tmp_path: Path):
    data = HandoffData(
        goal="x", completed=[], state="", remaining=[], files=[], decisions=[],
    )
    assert not (tmp_path / HANDOFF_DIR_NAME).exists()
    generate_handoff(data, tmp_path, ratio=0.0)
    assert (tmp_path / HANDOFF_DIR_NAME).is_dir()


# ---------------------------------------------------------------------------
# generate_handoff_via_llm — happy path
# ---------------------------------------------------------------------------


def test_generate_handoff_via_llm_writes_llm_content(tmp_path: Path):
    """LLM returns a well-formed markdown — we write it verbatim."""
    response = Mock()
    response.content = (
        "# Task Handoff Document\n\n"
        "**Generated**: 2026-05-22\n\n"
        "## 1. Original Goal\n\nRewrite auth.\n"
    )
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    messages = [
        {"role": "user", "content": "rewrite the auth flow"},
        {"role": "assistant", "content": "started reading auth.py"},
    ]
    path = _run(generate_handoff_via_llm(llm, messages, tmp_path, ratio=0.55))

    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Task Handoff Document")
    assert "Rewrite auth." in text
    # No fallback-marker comment when LLM succeeds
    assert "<!-- LLM handoff generation failed" not in text


def test_generate_handoff_via_llm_prepends_h1_if_missing(tmp_path: Path):
    """LLM might return body without the H1 header — provider patches it."""
    response = Mock()
    response.content = "## 1. Original Goal\n\nRewrite auth.\n"
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    path = _run(generate_handoff_via_llm(llm, [], tmp_path, ratio=0.3))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Task Handoff Document")


# ---------------------------------------------------------------------------
# generate_handoff_via_llm — failure → template fallback
# ---------------------------------------------------------------------------


def test_generate_handoff_via_llm_fallback_writes_once_with_marker(tmp_path: Path):
    """LLM failure: template content + trailing comment, single write only."""
    llm = Mock()
    llm.achat = AsyncMock(side_effect=RuntimeError("503 service unavailable"))

    messages = [
        {"role": "user", "content": "do the thing"},
        {"role": "assistant", "content": "started"},
    ]
    path = _run(generate_handoff_via_llm(llm, messages, tmp_path, ratio=0.5))

    text = path.read_text(encoding="utf-8")
    # The fallback must contain the LLM-failure breadcrumb
    assert "<!-- LLM handoff generation failed" in text
    assert "RuntimeError" in text
    # Template skeleton survived
    assert "## 1. Original Goal" in text
    # Goal extracted from the first user message
    assert "do the thing" in text


def test_generate_handoff_via_llm_fallback_includes_progress(tmp_path: Path):
    """Fallback merges progress.json steps when present."""
    progress_path = tmp_path / ".jayclaw" / "progress.json"
    progress_path.parent.mkdir()
    progress_path.write_text(
        json.dumps({
            "steps": [
                {"description": "step A", "status": "completed"},
                {"description": "step B", "status": "in_progress"},
                {"description": "step C", "status": "pending"},
            ]
        }),
        encoding="utf-8",
    )

    llm = Mock()
    llm.achat = AsyncMock(side_effect=RuntimeError("network down"))

    path = _run(generate_handoff_via_llm(
        llm, [{"role": "user", "content": "task X"}],
        tmp_path, ratio=0.5,
        progress_path=progress_path,
    ))

    text = path.read_text(encoding="utf-8")
    assert "- step A" in text  # completed
    assert "- step B" in text  # remaining (in_progress)
    assert "- step C" in text  # remaining (pending)


# ---------------------------------------------------------------------------
# find_latest_handoff
# ---------------------------------------------------------------------------


def test_find_latest_handoff_returns_none_when_empty(tmp_path: Path):
    assert find_latest_handoff(tmp_path) is None


def test_find_latest_handoff_finds_in_handoffs_dir(tmp_path: Path):
    d = tmp_path / HANDOFF_DIR_NAME
    d.mkdir()
    (d / "handoff_20260101_120000.md").write_text("old", encoding="utf-8")
    (d / "handoff_20260601_120000.md").write_text("new", encoding="utf-8")

    found = find_latest_handoff(tmp_path)
    assert found is not None
    assert found.name == "handoff_20260601_120000.md"


def test_find_latest_handoff_falls_back_to_legacy_sessions_dir(tmp_path: Path):
    """When HANDOFFS/ has none, falls back to .sessions/ (legacy location)."""
    d = tmp_path / ".sessions"
    d.mkdir()
    (d / "handoff_20250101_000000.md").write_text("legacy", encoding="utf-8")

    found = find_latest_handoff(tmp_path)
    assert found is not None
    assert "legacy" in found.read_text(encoding="utf-8")


def test_find_latest_handoff_prefers_new_dir_over_legacy(tmp_path: Path):
    new_d = tmp_path / HANDOFF_DIR_NAME
    new_d.mkdir()
    legacy_d = tmp_path / ".sessions"
    legacy_d.mkdir()
    (legacy_d / "handoff_20990101_000000.md").write_text("legacy newest", encoding="utf-8")
    (new_d / "handoff_20240101_000000.md").write_text("new dir oldest", encoding="utf-8")

    found = find_latest_handoff(tmp_path)
    # Iteration order is HANDOFFS/ first, so it wins regardless of timestamp
    assert "new dir oldest" in found.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# extract_handoff_data_from_history
# ---------------------------------------------------------------------------


def test_extract_handoff_data_uses_first_user_message_as_goal(tmp_path: Path):
    messages = [
        {"role": "user", "content": "fix the deadlock in worker.py"},
        {"role": "assistant", "content": "looking..."},
        {"role": "user", "content": "second message — not the goal"},
    ]
    data = extract_handoff_data_from_history(messages)
    assert data.goal.startswith("fix the deadlock")


def test_extract_handoff_data_truncates_long_goal(tmp_path: Path):
    messages = [{"role": "user", "content": "x" * 1000}]
    data = extract_handoff_data_from_history(messages)
    # 500-char cap
    assert len(data.goal) == 500


def test_extract_handoff_data_no_user_message(tmp_path: Path):
    data = extract_handoff_data_from_history([{"role": "assistant", "content": "hi"}])
    assert data.goal == ""


def test_extract_handoff_data_pulls_progress_steps(tmp_path: Path):
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(
        json.dumps({
            "steps": [
                {"description": "did A", "status": "completed"},
                {"description": "did B", "status": "completed"},
                {"description": "doing C", "status": "in_progress"},
                {"description": "later D", "status": "pending"},
                {"description": "skip E", "status": "skipped"},
            ]
        }),
        encoding="utf-8",
    )
    data = extract_handoff_data_from_history([], progress_path=progress_path)
    assert data.completed == ["did A", "did B"]
    assert data.remaining == ["doing C", "later D"]


def test_extract_handoff_data_handles_corrupt_progress_json(tmp_path: Path):
    progress_path = tmp_path / "progress.json"
    progress_path.write_text("{not valid json", encoding="utf-8")
    # Should swallow the parse error gracefully
    data = extract_handoff_data_from_history([], progress_path=progress_path)
    assert data.completed == []
    assert data.remaining == []


# ---------------------------------------------------------------------------
# _format_transcript / _format_progress (private helpers exercised via LLM call)
# ---------------------------------------------------------------------------


def test_llm_call_skips_empty_content_messages_in_transcript(tmp_path: Path):
    """Messages with empty/whitespace content are dropped before going to LLM."""
    from jay_coding_agent import handoff as handoff_mod

    captured: dict = {}

    class _CapturingLLM:
        async def achat(self, messages, temperature=0.2):  # noqa: D401
            captured["messages"] = messages
            response = Mock()
            response.content = "# Task Handoff Document\n\nok\n"
            return response

    messages = [
        {"role": "user", "content": "real goal"},
        {"role": "assistant", "content": ""},          # skipped
        {"role": "tool", "content": "   "},            # whitespace → skipped
        {"role": "assistant", "content": "real reply"},
        {"role": None, "content": "anon"},             # role defaults to "?"
    ]
    _run(generate_handoff_via_llm(_CapturingLLM(), messages, tmp_path, ratio=0.5))

    transcript = captured["messages"][1].content
    # Skipped messages don't show up
    assert "### ASSISTANT\n\n" not in transcript
    # Real ones do
    assert "real goal" in transcript
    assert "real reply" in transcript
    # Missing role becomes "?"
    assert "### ?" in transcript


def test_llm_call_truncates_oversized_transcript(tmp_path: Path):
    """Transcript over max_chars is head/tail-clipped with a marker."""
    captured: dict = {}

    class _CapturingLLM:
        async def achat(self, messages, temperature=0.2):
            captured["messages"] = messages
            response = Mock()
            response.content = "# Task Handoff Document\n\nok\n"
            return response

    # Build a transcript well above the 24000-char threshold.
    huge = [{"role": "user", "content": "A" * 30_000}]
    _run(generate_handoff_via_llm(_CapturingLLM(), huge, tmp_path, ratio=0.5))

    transcript = captured["messages"][1].content
    assert "transcript truncated for length" in transcript
    # Both ends survive; middle is dropped
    assert transcript.count("A") < 30_000


def test_llm_call_progress_summary_unreadable_json(tmp_path: Path):
    """Corrupt progress.json on the LLM-path surfaces the unreadable marker."""
    progress_path = tmp_path / "progress.json"
    progress_path.write_text("{broken", encoding="utf-8")

    captured: dict = {}

    class _CapturingLLM:
        async def achat(self, messages, temperature=0.2):
            captured["messages"] = messages
            response = Mock()
            response.content = "# Task Handoff Document\n\nok\n"
            return response

    _run(generate_handoff_via_llm(
        _CapturingLLM(), [{"role": "user", "content": "x"}],
        tmp_path, ratio=0.5, progress_path=progress_path,
    ))

    user_prompt = captured["messages"][1].content
    assert "_(progress.json unreadable)_" in user_prompt


def test_llm_call_progress_summary_no_steps(tmp_path: Path):
    """progress.json with no 'steps' key surfaces the no-steps marker."""
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(json.dumps({"other": "data"}), encoding="utf-8")

    captured: dict = {}

    class _CapturingLLM:
        async def achat(self, messages, temperature=0.2):
            captured["messages"] = messages
            response = Mock()
            response.content = "# Task Handoff Document\n\nok\n"
            return response

    _run(generate_handoff_via_llm(
        _CapturingLLM(), [{"role": "user", "content": "x"}],
        tmp_path, ratio=0.5, progress_path=progress_path,
    ))

    user_prompt = captured["messages"][1].content
    assert "_(no steps recorded)_" in user_prompt


def test_llm_call_transcript_empty_when_no_messages(tmp_path: Path):
    """Empty message list yields the empty marker in the LLM prompt."""
    captured: dict = {}

    class _CapturingLLM:
        async def achat(self, messages, temperature=0.2):
            captured["messages"] = messages
            response = Mock()
            response.content = "# Task Handoff Document\n\nok\n"
            return response

    _run(generate_handoff_via_llm(_CapturingLLM(), [], tmp_path, ratio=0.5))
    assert "_(empty)_" in captured["messages"][1].content

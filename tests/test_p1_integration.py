"""Integration test: P1-1 through P1-4 work together."""

import asyncio
import json
from pathlib import Path

import pytest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_p1_1_read_knowledge_registered():
    from jay_agent_core.tools.handlers_core import HANDLERS
    from jay_agent_core.tools.schemas import CORE_TOOL_NAMES
    assert "read_knowledge" in HANDLERS
    assert "read_knowledge" in CORE_TOOL_NAMES


def test_p1_2_update_progress_registered():
    from jay_agent_core.tools.handlers_core import HANDLERS
    assert "update_progress" in HANDLERS


def test_p1_3_e2e_module_importable():
    from jay_agent_tools.e2e import cli_check, http_check, CheckResult, CheckStatus
    assert callable(cli_check)
    assert callable(http_check)


def test_p1_4_context_utilization():
    from jay_agent_core.context import compute_utilization, CompressionConfig
    config = CompressionConfig()
    assert config.user_decision_threshold == 0.4
    util = compute_utilization([], max_tokens=1000, config=config)
    assert util.zone == "smart"


def test_p1_4_handoff_module():
    from jay_coding_agent.handoff import HandoffData, generate_handoff, find_latest_handoff
    assert callable(generate_handoff)


def test_progress_and_handoff_interop(tmp_path):
    """A completed progress.json should feed into handoff generation."""
    from jay_agent_core.tools.handlers_core import handle_update_progress
    from jay_coding_agent.handoff import extract_handoff_data_from_history

    _run(handle_update_progress(
        {"action": "init", "goal": "Build X", "steps": ["A", "B", "C"]},
        "u", {"workspace": str(tmp_path)}, None
    ))
    _run(handle_update_progress(
        {"action": "advance", "step_id": 1, "step_status": "completed"},
        "u", {"workspace": str(tmp_path)}, None
    ))

    progress_path = tmp_path / ".agents" / "progress.json"
    data = extract_handoff_data_from_history(
        [{"role": "user", "content": "Build X"}],
        progress_path,
    )
    assert "A" in data.completed
    assert "B" in data.remaining
    assert "C" in data.remaining

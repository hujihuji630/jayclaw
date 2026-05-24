"""Tests for progress tracking."""

import asyncio
import json
from pathlib import Path

import pytest

from jay_agent_core.progress import Progress, Step
from jay_agent_core.tools.handlers_core import handle_update_progress


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_progress_init_and_save(tmp_path):
    progress = Progress(goal="Test task", steps=[Step(id=1, description="Step 1")])
    path = progress.save(tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["goal"] == "Test task"
    assert data["status"] == "in_progress"


def test_progress_advance(tmp_path):
    progress = Progress(goal="Test", steps=[Step(id=1, description="S1"), Step(id=2, description="S2")])
    progress.advance(1, "completed")
    assert progress.steps[0].status == "completed"
    assert progress.status == "in_progress"
    progress.advance(2, "completed")
    assert progress.status == "completed"


def test_progress_load(tmp_path):
    progress = Progress(goal="Load test", steps=[Step(id=1, description="S1")])
    progress.save(tmp_path)
    loaded = Progress.load(tmp_path)
    assert loaded is not None
    assert loaded.goal == "Load test"


def test_handler_init(tmp_path):
    result = _run(handle_update_progress(
        {"action": "init", "goal": "Build feature", "steps": ["Design", "Implement", "Test"]},
        "test", {"workspace": str(tmp_path)}, None
    ))
    assert result.ok is True
    assert result.data["total_steps"] == 3
    assert (tmp_path / ".jayclaw" / "progress.json").exists()


def test_handler_advance(tmp_path):
    _run(handle_update_progress(
        {"action": "init", "goal": "G", "steps": ["S1"]},
        "test", {"workspace": str(tmp_path)}, None
    ))
    result = _run(handle_update_progress(
        {"action": "advance", "step_id": 1, "step_status": "completed"},
        "test", {"workspace": str(tmp_path)}, None
    ))
    assert result.ok is True
    assert result.data["status"] == "completed"


def test_handler_fail(tmp_path):
    _run(handle_update_progress(
        {"action": "init", "goal": "G", "steps": ["S1"]},
        "test", {"workspace": str(tmp_path)}, None
    ))
    result = _run(handle_update_progress(
        {"action": "fail"}, "test", {"workspace": str(tmp_path)}, None
    ))
    assert result.ok is True
    assert result.data["status"] == "failed"

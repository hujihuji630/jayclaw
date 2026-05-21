"""Tests for context utilization tracking."""

from jay_agent_core.context import (
    CompressionConfig,
    ContextUtilization,
    compute_utilization,
)


def test_smart_zone():
    config = CompressionConfig()
    messages = [{"role": "user", "content": "hi"}]
    util = compute_utilization(messages, max_tokens=10000, config=config)
    assert util.zone == "smart"
    assert util.ratio < 0.4
    assert util.should_prompt_user is False


def test_warning_zone():
    config = CompressionConfig()
    big_content = "x" * 250
    messages = [{"role": "user", "content": big_content}]
    util = compute_utilization(messages, max_tokens=100, config=config)
    assert util.zone == "warning"
    assert 0.4 <= util.ratio < 0.7


def test_compressed_zone():
    big_content = "x" * 500
    messages = [{"role": "user", "content": big_content}]
    util = compute_utilization(messages, max_tokens=100)
    assert util.zone == "compressed"


def test_should_prompt_user_on_crossing():
    """Should prompt only when crossing 40% threshold from below."""
    messages = [{"role": "user", "content": "x" * 250}]
    util = compute_utilization(messages, max_tokens=100, previous_ratio=0.2)
    assert util.should_prompt_user is True


def test_no_prompt_if_already_above():
    """Should NOT prompt if previous ratio was already above 40%."""
    messages = [{"role": "user", "content": "x" * 250}]
    util = compute_utilization(messages, max_tokens=100, previous_ratio=0.5)
    assert util.should_prompt_user is False


def test_no_prompt_if_below_threshold():
    messages = [{"role": "user", "content": "hi"}]
    util = compute_utilization(messages, max_tokens=10000, previous_ratio=0.1)
    assert util.should_prompt_user is False


def test_percent_property():
    messages = [{"role": "user", "content": "x" * 1000}]
    util = compute_utilization(messages, max_tokens=1000)
    assert isinstance(util.percent, int)
    assert 0 <= util.percent <= 200


def test_handoff_generation(tmp_path):
    from jay_coding_agent.handoff import HandoffData, generate_handoff

    data = HandoffData(
        goal="Build feature X",
        completed=["Design API", "Write tests"],
        state="Implementation half done",
        remaining=["Wire UI", "Deploy"],
        files=["src/api.py"],
        decisions=["Use REST not GraphQL"],
    )
    path = generate_handoff(data, tmp_path, ratio=0.45)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Build feature X" in content
    assert "Design API" in content
    assert "45%" in content


def test_find_latest_handoff(tmp_path):
    from jay_coding_agent.handoff import find_latest_handoff

    assert find_latest_handoff(tmp_path) is None

    sessions = tmp_path / ".sessions"
    sessions.mkdir()
    (sessions / "handoff_20260101_120000.md").write_text("old", encoding="utf-8")
    (sessions / "handoff_20260301_120000.md").write_text("new", encoding="utf-8")

    latest = find_latest_handoff(tmp_path)
    assert latest is not None
    assert "20260301" in latest.name

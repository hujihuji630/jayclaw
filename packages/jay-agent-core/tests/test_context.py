"""Tests for context management."""

import pytest
from jay_agent_core.context import ContextManager


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_context_manager_creation(temp_workspace):
    """Test creating context manager."""
    ctx = ContextManager(temp_workspace)
    assert ctx.workspace == temp_workspace


def test_find_agents_md(temp_workspace):
    """Test finding AGENTS.md files."""
    ctx = ContextManager(temp_workspace)

    # Create AGENTS.md in workspace
    (temp_workspace / "AGENTS.md").write_text("# Project context")

    # Create in .jayclaw
    agents_dir = temp_workspace / ".jayclaw"
    agents_dir.mkdir()
    (agents_dir / "AGENTS.md").write_text("# More context")

    files = ctx.find_context_files("AGENTS.md")
    assert len(files) >= 1


def test_load_agents_md(temp_workspace):
    """Test loading AGENTS.md."""
    ctx = ContextManager(temp_workspace)

    (temp_workspace / "AGENTS.md").write_text("# Project\nContext here")

    content = ctx.load_agents_md()
    assert content is not None
    assert "Project" in content


def test_load_system_md(temp_workspace):
    """Test loading SYSTEM.md."""
    ctx = ContextManager(temp_workspace)

    (temp_workspace / "SYSTEM.md").write_text("Custom system prompt")

    content = ctx.load_system_md()
    assert content == "Custom system prompt"


def test_load_append_system_md(temp_workspace):
    """Test loading APPEND_SYSTEM.md."""
    ctx = ContextManager(temp_workspace)

    (temp_workspace / "APPEND_SYSTEM.md").write_text("Additional instructions")

    content = ctx.load_append_system_md()
    assert content == "Additional instructions"


def test_build_system_prompt_default(temp_workspace):
    """Test building system prompt with no overrides."""
    ctx = ContextManager(temp_workspace)

    default = "Default prompt"
    result = ctx.build_system_prompt(default)

    assert result == default


def test_build_system_prompt_with_override(temp_workspace):
    """Test system prompt with SYSTEM.md override."""
    ctx = ContextManager(temp_workspace)

    (temp_workspace / "SYSTEM.md").write_text("Override prompt")

    default = "Default prompt"
    result = ctx.build_system_prompt(default)

    assert "Override prompt" in result
    assert "Default prompt" not in result


def test_build_system_prompt_with_agents_md(temp_workspace):
    """Test system prompt with AGENTS.md."""
    ctx = ContextManager(temp_workspace)

    (temp_workspace / "AGENTS.md").write_text("Project context")

    default = "Default prompt"
    result = ctx.build_system_prompt(default)

    assert "Default prompt" in result
    assert "Project context" in result


def test_build_system_prompt_with_append(temp_workspace):
    """Test system prompt with APPEND_SYSTEM.md."""
    ctx = ContextManager(temp_workspace)

    (temp_workspace / "APPEND_SYSTEM.md").write_text("Extra instructions")

    default = "Default prompt"
    result = ctx.build_system_prompt(default)

    assert "Default prompt" in result
    assert "Extra instructions" in result


def test_find_context_files_hierarchy(temp_workspace):
    """Test finding files in hierarchy."""
    ContextManager(temp_workspace)

    # Create nested structure
    subdir = temp_workspace / "subdir"
    subdir.mkdir()

    (temp_workspace / "AGENTS.md").write_text("Parent")
    (subdir / "AGENTS.md").write_text("Child")

    # Search from subdir
    ctx_sub = ContextManager(subdir)
    files = ctx_sub.find_context_files("AGENTS.md")

    # Should find both
    assert len(files) >= 2


def test_compute_utilization_caches_unchanged_messages():
    """Calling compute_utilization twice with same messages should not re-tokenize."""
    from jay_agent_core.context import ContextManager

    cm = ContextManager()
    msgs = [
        {'id': 'a', 'role': 'user', 'content': 'hello ' * 100},
        {'id': 'b', 'role': 'assistant', 'content': 'world ' * 100},
    ]
    u1 = cm.compute_utilization(msgs, max_tokens=8000, model='gpt-4')
    u2 = cm.compute_utilization(msgs, max_tokens=8000, model='gpt-4')
    assert u1.current_tokens == u2.current_tokens
    assert cm._cache_hits >= 2, f"expected >=2 cache hits on second call, got {cm._cache_hits}"


def test_compute_utilization_only_tokenizes_new_messages():
    """Adding a single message and recomputing should only tokenize the new one."""
    from jay_agent_core.context import ContextManager

    cm = ContextManager()
    msgs = [{'id': 'a', 'role': 'user', 'content': 'hello ' * 100}]
    cm.compute_utilization(msgs, max_tokens=8000, model='gpt-4')

    msgs.append({'id': 'b', 'role': 'assistant', 'content': 'world ' * 50})
    cm._tokenize_calls = 0
    cm.compute_utilization(msgs, max_tokens=8000, model='gpt-4')
    # Only message 'b' should require tokenization the second pass.
    assert cm._tokenize_calls == 1, f"expected only 1 tokenize call, got {cm._tokenize_calls}"

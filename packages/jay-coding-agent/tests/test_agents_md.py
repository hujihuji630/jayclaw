"""Tests for per-workspace AGENTS.md generation and session-end summarization."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from jay_coding_agent.agents_md import (
    DEFAULT_ALWAYS_LOADED,
    INITIAL_TEMPLATE,
    WorkspaceSnapshot,
    _merge_into_section,
    _parse_summary_json,
    _strip_empty_placeholder,
    append_session_summary,
    generate_initial,
    scan_workspace,
)


# ---------------------------------------------------------------------------
# scan_workspace
# ---------------------------------------------------------------------------


def test_scan_detects_python_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my-pkg"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# my-pkg\n\nA cool project.", encoding="utf-8")

    snap = scan_workspace(tmp_path)

    assert snap.project_type == "python"
    assert snap.project_name == "my-pkg"
    assert "pyproject.toml" in snap.config_files
    assert "src/" in snap.top_level
    assert "tests/" in snap.top_level
    assert "README.md" in snap.top_level
    assert "my-pkg" in snap.readme_excerpt


def test_scan_detects_node_project(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "frontend-app", "version": "1.0.0"}', encoding="utf-8"
    )

    snap = scan_workspace(tmp_path)

    assert snap.project_type == "node"
    assert snap.project_name == "frontend-app"


def test_scan_skips_known_dirs(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "src").mkdir()

    snap = scan_workspace(tmp_path)

    assert "src/" in snap.top_level
    assert ".git/" not in snap.top_level
    assert "node_modules/" not in snap.top_level
    assert "__pycache__/" not in snap.top_level


def test_scan_unknown_project(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    snap = scan_workspace(tmp_path)

    assert snap.project_type == "unknown"
    assert snap.project_name == tmp_path.name
    assert "notes.txt" in snap.top_level


def test_scan_render_includes_sections(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n", encoding="utf-8")
    snap = scan_workspace(tmp_path)
    rendered = snap.render()

    assert "Project type" in rendered
    assert "Top-level entries" in rendered
    assert "Config files" in rendered


# ---------------------------------------------------------------------------
# _parse_summary_json
# ---------------------------------------------------------------------------


def test_parse_summary_json_plain():
    text = '{"new_pitfalls": ["a"], "new_constraints": []}'
    parsed = _parse_summary_json(text)
    assert parsed == {"new_pitfalls": ["a"], "new_constraints": []}


def test_parse_summary_json_strips_fences():
    text = '```json\n{"new_pitfalls": ["x"]}\n```'
    parsed = _parse_summary_json(text)
    assert parsed == {"new_pitfalls": ["x"]}


def test_parse_summary_json_with_prose_around():
    text = 'Here is the result:\n\n```json\n{"a": 1}\n```\n\nLet me know.'
    parsed = _parse_summary_json(text)
    assert parsed == {"a": 1}


def test_parse_summary_json_invalid_returns_empty():
    assert _parse_summary_json("not even close") == {}
    assert _parse_summary_json("") == {}
    assert _parse_summary_json("```json\nbroken {\n```") == {}


def test_parse_summary_json_array_returns_empty():
    """Top-level arrays are not the contract — return empty dict."""
    assert _parse_summary_json("[1, 2, 3]") == {}


# ---------------------------------------------------------------------------
# _merge_into_section
# ---------------------------------------------------------------------------


SAMPLE_AGENTS_MD = """# AGENTS.md

## Always Loaded

- existing rule 1
- existing rule 2

## Knowledge Map

- **topic-x** — when to read

## Known Pitfalls

- 2025-01: old lesson

## How to Use This Map

- Notes
"""


def test_merge_into_section_appends_to_target_only():
    new = _merge_into_section(SAMPLE_AGENTS_MD, "## Always Loaded", ["- new rule"])

    assert "- existing rule 1" in new
    assert "- existing rule 2" in new
    assert "- new rule" in new
    # Other sections untouched
    assert "- **topic-x** — when to read" in new
    assert "- 2025-01: old lesson" in new
    # New rule sits in Always Loaded, before Knowledge Map heading
    always_idx = new.index("## Always Loaded")
    kmap_idx = new.index("## Knowledge Map")
    new_rule_idx = new.index("- new rule")
    assert always_idx < new_rule_idx < kmap_idx


def test_merge_into_section_preserves_blank_line_before_next_heading():
    new = _merge_into_section(SAMPLE_AGENTS_MD, "## Known Pitfalls", ["- 2025-05: fresh lesson"])

    # The blank line separating Known Pitfalls from "How to Use This Map" survives
    assert "- 2025-05: fresh lesson\n\n## How to Use This Map" in new


def test_merge_into_section_appends_at_end_when_section_is_last():
    md = "# X\n\n## Only Section\n\n- a\n"
    new = _merge_into_section(md, "## Only Section", ["- b"])
    assert new.endswith("- a\n- b\n") or new.endswith("- a\n- b")


def test_merge_into_section_creates_section_if_missing():
    md = "# X\n\n## Other\n\n- foo\n"
    new = _merge_into_section(md, "## Always Loaded", ["- new"])
    assert "## Always Loaded" in new
    assert "- new" in new


def test_merge_into_section_empty_lines_no_change():
    new = _merge_into_section(SAMPLE_AGENTS_MD, "## Always Loaded", [])
    assert new == SAMPLE_AGENTS_MD


# ---------------------------------------------------------------------------
# _strip_empty_placeholder
# ---------------------------------------------------------------------------


def test_strip_empty_placeholder_removes_target_only():
    md = (
        "## Known Pitfalls\n"
        "\n"
        "_(empty — yet)_\n"
        "\n"
        "## Other\n"
        "\n"
        "_(empty — keep me)_\n"
    )
    out = _strip_empty_placeholder(md, "## Known Pitfalls")
    assert "_(empty — yet)_" not in out
    assert "_(empty — keep me)_" in out


# ---------------------------------------------------------------------------
# Initial template
# ---------------------------------------------------------------------------


def test_initial_template_has_three_sections():
    rendered = INITIAL_TEMPLATE.format(
        always_loaded="- a",
        knowledge_map="- **t** — when",
    )
    assert "## Always Loaded" in rendered
    assert "## Knowledge Map" in rendered
    assert "## Known Pitfalls" in rendered


# ---------------------------------------------------------------------------
# generate_initial (LLM mocked)
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_generate_initial_writes_file_with_llm_response(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n", encoding="utf-8")

    response = Mock()
    response.content = (
        '{"always_loaded": ["never commit secrets", "run pytest before pushing"], '
        '"knowledge_map": ["- **build** — when changing CI"]}'
    )
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    path = _run(generate_initial(tmp_path, llm))

    assert path == tmp_path / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    assert "never commit secrets" in text
    assert "run pytest before pushing" in text
    assert "- **build** — when changing CI" in text
    assert "## Always Loaded" in text
    assert "## Known Pitfalls" in text


def test_generate_initial_falls_back_when_llm_fails(tmp_path: Path):
    llm = Mock()
    llm.achat = AsyncMock(side_effect=RuntimeError("boom"))

    path = _run(generate_initial(tmp_path, llm))

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # Defaults kicked in
    for default in DEFAULT_ALWAYS_LOADED:
        assert default in text


def test_generate_initial_falls_back_on_invalid_json(tmp_path: Path):
    response = Mock()
    response.content = "not valid json"
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    path = _run(generate_initial(tmp_path, llm))

    text = path.read_text(encoding="utf-8")
    for default in DEFAULT_ALWAYS_LOADED:
        assert default in text


# ---------------------------------------------------------------------------
# append_session_summary (LLM mocked)
# ---------------------------------------------------------------------------


def test_append_session_summary_returns_diff_and_parsed(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text(SAMPLE_AGENTS_MD, encoding="utf-8")

    response = Mock()
    response.content = (
        '{"new_pitfalls": ["forgot to read README before refactoring"], '
        '"new_constraints": ["always run ruff before commit"]}'
    )
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    history = [
        {"role": "user", "content": "fix the auth bug"},
        {"role": "assistant", "content": "i'll start refactoring..."},
        {"role": "user", "content": "no — read the README first next time"},
    ]

    new_content, diff, parsed = _run(
        append_session_summary(tmp_path, llm, history, target)
    )

    assert "always run ruff before commit" in new_content
    assert "forgot to read README before refactoring" in new_content
    assert diff  # non-empty unified diff
    assert parsed["new_pitfalls"] == ["forgot to read README before refactoring"]
    assert parsed["new_constraints"] == ["always run ruff before commit"]
    # File is NOT yet written (caller's responsibility)
    assert target.read_text(encoding="utf-8") == SAMPLE_AGENTS_MD


def test_append_session_summary_no_changes_when_empty(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text(SAMPLE_AGENTS_MD, encoding="utf-8")

    response = Mock()
    response.content = '{"new_pitfalls": [], "new_constraints": []}'
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    new_content, diff, parsed = _run(
        append_session_summary(tmp_path, llm, [{"role": "user", "content": "hi"}], target)
    )

    assert new_content == SAMPLE_AGENTS_MD
    assert diff == ""
    assert parsed == {"new_pitfalls": [], "new_constraints": []}


def test_append_session_summary_raises_on_missing_file(tmp_path: Path):
    llm = Mock()
    llm.achat = AsyncMock()

    with pytest.raises(FileNotFoundError):
        _run(append_session_summary(tmp_path, llm, [], tmp_path / "AGENTS.md"))


def test_append_session_summary_strips_pitfalls_placeholder(tmp_path: Path):
    target = tmp_path / "AGENTS.md"
    target.write_text(
        INITIAL_TEMPLATE.format(
            always_loaded="- existing", knowledge_map="_(empty)_"
        ),
        encoding="utf-8",
    )

    response = Mock()
    response.content = '{"new_pitfalls": ["lesson one"], "new_constraints": []}'
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    new_content, _, _ = _run(
        append_session_summary(tmp_path, llm, [{"role": "user", "content": "x"}], target)
    )

    assert "_(empty — 会话结束后" not in new_content
    assert "lesson one" in new_content


def test_append_session_summary_handles_message_objects(tmp_path: Path):
    """Should accept jay_llm.Message-like objects (with .role / .content), not just dicts."""

    class FakeMsg:
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content

    target = tmp_path / "AGENTS.md"
    target.write_text(SAMPLE_AGENTS_MD, encoding="utf-8")

    response = Mock()
    response.content = '{"new_pitfalls": ["dont skip the README"], "new_constraints": []}'
    llm = Mock()
    llm.achat = AsyncMock(return_value=response)

    history = [FakeMsg("user", "hi"), FakeMsg("assistant", "hello")]

    new_content, _, parsed = _run(
        append_session_summary(tmp_path, llm, history, target)
    )

    assert "dont skip the README" in new_content
    assert parsed["new_pitfalls"] == ["dont skip the README"]

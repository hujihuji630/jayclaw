"""Tests for LintFinding base contract."""

from pathlib import Path

import pytest

from jay_agent_tools.linters.base import LintFinding


def test_finding_render_includes_suggestion():
    f = LintFinding(
        file=Path("foo.py"),
        line=42,
        code="JCXXX",
        message="boom",
        suggestion="fix it",
    )
    rendered = f.render()
    assert "JCXXX" in rendered
    assert "fix it" in rendered
    assert "foo.py:42" in rendered


def test_render_with_autofix():
    f = LintFinding(
        file=Path("a.py"),
        line=1,
        code="JC001",
        message="m",
        suggestion="s",
        autofix="logger.info(...)",
    )
    rendered = f.render()
    assert "autofix" in rendered
    assert "logger.info" in rendered


def test_empty_suggestion_rejected():
    with pytest.raises(ValueError):
        LintFinding(
            file=Path("x.py"),
            line=1,
            code="T",
            message="m",
            suggestion="",
        )


def test_whitespace_suggestion_rejected():
    with pytest.raises(ValueError):
        LintFinding(
            file=Path("x.py"),
            line=1,
            code="T",
            message="m",
            suggestion="   ",
        )

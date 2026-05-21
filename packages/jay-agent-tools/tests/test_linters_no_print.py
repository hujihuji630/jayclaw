"""Tests for NoPrintLinter (JC001)."""

from pathlib import Path

from jay_agent_tools.linters.no_print import NoPrintLinter


def test_detects_print_call():
    src = "def foo():\n    print('hi')\n"
    findings = NoPrintLinter().check(Path("src/app.py"), src)
    assert len(findings) == 1
    assert findings[0].code == "JC001"
    assert findings[0].suggestion
    assert findings[0].line == 2


def test_no_findings_without_print():
    src = "import logging\nlogger = logging.getLogger(__name__)\n"
    assert NoPrintLinter().check(Path("src/app.py"), src) == []


def test_skips_test_directory():
    src = "def test_foo():\n    print('debug')\n"
    assert NoPrintLinter().check(Path("packages/x/tests/test_app.py"), src) == []


def test_noqa_escape():
    src = "def foo():\n    print('hi')  # noqa: JC001\n"
    assert NoPrintLinter().check(Path("src/app.py"), src) == []


def test_handles_syntax_error():
    src = "def foo("
    assert NoPrintLinter().check(Path("broken.py"), src) == []


def test_suggestion_non_empty():
    src = "print('x')\n"
    findings = NoPrintLinter().check(Path("src/y.py"), src)
    assert findings
    for f in findings:
        assert f.suggestion.strip()

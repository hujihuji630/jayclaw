"""Tests for InternalFieldLinter (JC003)."""

from pathlib import Path

from jay_agent_tools.linters.internal_field import InternalFieldLinter


def test_detects_internal_field_without_underscore():
    src = '''
schema = {
    "properties": {
        "query": {"type": "string"},
        "internal": {"type": "boolean"},
    }
}
'''
    findings = InternalFieldLinter().check(Path("s.py"), src)
    assert any(f.code == "JC003" and "internal" in f.message for f in findings)
    assert findings[0].suggestion


def test_accepts_underscore_prefixed_internal():
    src = '''
schema = {
    "properties": {
        "_internal": {"type": "boolean"},
    }
}
'''
    assert InternalFieldLinter().check(Path("s.py"), src) == []


def test_no_finding_for_normal_fields():
    src = '''
schema = {
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer"},
    }
}
'''
    assert InternalFieldLinter().check(Path("s.py"), src) == []


def test_detects_skip_llm_marker():
    src = '''
schema = {
    "properties": {
        "skip_llm": {"type": "boolean"},
    }
}
'''
    findings = InternalFieldLinter().check(Path("s.py"), src)
    assert any(f.code == "JC003" for f in findings)


def test_suggestion_non_empty():
    src = '''
schema = {
    "properties": {
        "permission": {"type": "string"},
    }
}
'''
    findings = InternalFieldLinter().check(Path("s.py"), src)
    for f in findings:
        assert f.suggestion.strip()

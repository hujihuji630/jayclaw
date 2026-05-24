"""Tests for jay_web_ui.server._safe_join — the path-traversal guard used by
/api/upload, /api/files DELETE, and /api/agents-md/summarize-write.

These tests pin the security contract so the guard can't silently regress
during future refactors of server.py.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from jay_web_ui.server import _safe_join


def test_safe_join_simple_filename(tmp_path):
    """Plain filename joins under the base."""
    out = _safe_join(tmp_path, "hello.txt")
    assert out == (tmp_path / "hello.txt").resolve()


def test_safe_join_strips_directory_components(tmp_path):
    """Forward-slash and backslash directory parts get stripped to basename."""
    out = _safe_join(tmp_path, "subdir/leaf.txt")
    assert out.name == "leaf.txt"
    assert out.parent.resolve() == tmp_path.resolve()

    out2 = _safe_join(tmp_path, "subdir\\winleaf.txt")
    assert out2.name == "winleaf.txt"
    assert out2.parent.resolve() == tmp_path.resolve()


def test_safe_join_rejects_dotdot(tmp_path):
    """``..`` traversal is reduced to basename — never escapes."""
    # PurePosixPath(...).name on "../etc/passwd" yields "passwd" not "..".
    out = _safe_join(tmp_path, "../etc/passwd")
    assert out.name == "passwd"
    assert out.parent.resolve() == tmp_path.resolve()


def test_safe_join_rejects_pure_dotdot(tmp_path):
    """A bare `..` filename is refused outright."""
    with pytest.raises(HTTPException) as exc_info:
        _safe_join(tmp_path, "..")
    assert exc_info.value.status_code == 400


def test_safe_join_rejects_pure_dot(tmp_path):
    """A bare `.` filename is refused outright."""
    with pytest.raises(HTTPException) as exc_info:
        _safe_join(tmp_path, ".")
    assert exc_info.value.status_code == 400


def test_safe_join_rejects_empty_string(tmp_path):
    with pytest.raises(HTTPException) as exc_info:
        _safe_join(tmp_path, "")
    assert exc_info.value.status_code == 400


def test_safe_join_rejects_whitespace_only(tmp_path):
    """Whitespace-only filenames are refused as invalid (400)."""
    with pytest.raises(HTTPException) as exc_info:
        _safe_join(tmp_path, "   ")
    assert exc_info.value.status_code == 400


def test_safe_join_unicode_filename(tmp_path):
    """Unicode filenames pass through (not stripped to '?')."""
    out = _safe_join(tmp_path, "中文文件.md")
    assert out.name == "中文文件.md"
    assert out.parent.resolve() == tmp_path.resolve()


def test_safe_join_absolute_path_input(tmp_path):
    """Absolute Linux path: basename only, lands inside base."""
    out = _safe_join(tmp_path, "/etc/passwd")
    assert out.name == "passwd"
    assert out.parent.resolve() == tmp_path.resolve()


def test_safe_join_windows_drive_path_input(tmp_path):
    """Windows-style drive paths: backslashes normalized then basename taken."""
    out = _safe_join(tmp_path, "C:\\Windows\\System32\\config\\SAM")
    assert out.name == "SAM"
    assert out.parent.resolve() == tmp_path.resolve()


def test_safe_join_preserves_extensions(tmp_path):
    """Multi-dot filenames retain their full extension."""
    out = _safe_join(tmp_path, "evidence.tar.gz")
    assert out.name == "evidence.tar.gz"


def test_safe_join_rejects_null_byte(tmp_path):
    """Null byte in filename is refused as 400 — it's a known path-truncation
    attack vector on some C-backed OS APIs.
    """
    with pytest.raises(HTTPException) as exc_info:
        _safe_join(tmp_path, "evil\x00.txt")
    assert exc_info.value.status_code == 400


def test_safe_join_long_filename(tmp_path):
    """Very long filenames — should still resolve, no crash."""
    long_name = "a" * 200 + ".txt"
    out = _safe_join(tmp_path, long_name)
    assert out.name == long_name


def test_safe_join_symlink_escape_is_caught(tmp_path):
    """Defense-in-depth: even if a symlink in ``base`` points outside ``base``,
    the final ``relative_to`` check refuses the resolved path with 400.

    On Windows symlinks usually require admin or developer mode, so skip.
    """
    import os

    if os.name == "nt":
        import pytest as _pytest
        _pytest.skip("symlink creation needs developer mode on Windows")

    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_target = outside / "secret.txt"
    outside_target.write_text("ssh keys", encoding="utf-8")

    # Place a symlink inside base pointing outside.
    link_in_base = base / "secret.txt"
    link_in_base.symlink_to(outside_target)

    with pytest.raises(HTTPException) as exc_info:
        _safe_join(base, "secret.txt")
    assert exc_info.value.status_code == 400
    assert "escape" in exc_info.value.detail

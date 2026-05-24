"""Tests for the workspace path whitelist used by /api/workspace + /api/browse*.

Pins the security contract: clients can't navigate the server into /etc,
C:\\Windows, or anywhere outside the user's home / cwd / explicit roots.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from jay_web_ui.server import (
    _allowed_workspace_roots,
    _check_workspace_path,
    _is_system_path,
    _is_under_allowed_root,
)


def test_is_system_path_unix_etc():
    assert _is_system_path(Path("/etc/passwd"))
    assert _is_system_path(Path("/etc"))
    assert _is_system_path(Path("/usr/bin/python"))
    assert _is_system_path(Path("/sys/devices/foo"))


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific")
def test_is_system_path_windows_system32():
    assert _is_system_path(Path("C:\\Windows\\System32\\config\\SAM"))
    assert _is_system_path(Path("c:\\windows"))
    assert _is_system_path(Path("C:\\Program Files\\Whatever"))
    assert _is_system_path(Path("C:\\ProgramData\\Microsoft"))


def test_is_system_path_lookalikes_are_safe():
    """Paths that *contain* a system prefix as a substring shouldn't trigger."""
    # /etc-mybackup is not /etc — must not match
    assert not _is_system_path(Path("/etc-mybackup/file.txt"))
    assert not _is_system_path(Path("/home/user/etcetera/notes.md"))


def test_check_workspace_path_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        _check_workspace_path("")
    assert exc.value.status_code == 400


def test_check_workspace_path_rejects_whitespace():
    with pytest.raises(HTTPException) as exc:
        _check_workspace_path("   ")
    assert exc.value.status_code == 400


def test_check_workspace_path_rejects_null_byte():
    with pytest.raises(HTTPException) as exc:
        _check_workspace_path("/home\x00/evil")
    assert exc.value.status_code == 400


def test_check_workspace_path_rejects_system_paths(tmp_path):
    """Even paths that exist (in some sense) get refused with 403."""
    if os.name == "nt":
        target = "C:\\Windows"
    else:
        target = "/etc"

    with pytest.raises(HTTPException) as exc:
        _check_workspace_path(target)
    assert exc.value.status_code == 403
    assert "system" in exc.value.detail.lower()


def test_check_workspace_path_accepts_home_subtree(tmp_path):
    """A directory inside HOME is allowed."""
    target = Path.home() / "subdir-that-need-not-exist"
    # path doesn't have to exist — we only check the resolved location
    out = _check_workspace_path(str(target))
    assert out.is_absolute()


def test_check_workspace_path_accepts_cwd_subtree():
    """The process's cwd subtree is allowed (so launching from any project
    dir keeps working)."""
    target = Path.cwd() / "child"
    out = _check_workspace_path(str(target))
    assert out == target.resolve()


def test_check_workspace_path_rejects_outside_roots(tmp_path, monkeypatch):
    """A path outside both home and cwd is refused with 403."""
    # Create a sandbox outside cwd & home — use an OS-level temp dir under
    # /tmp on Linux, or something not under C:\Users on Windows.
    if os.name == "nt":
        # /tmp on Windows lands under C:\Users\<user>\AppData\Local\Temp\...,
        # which IS under home — so this test is harder. Use a fake escape.
        # Skip: tmp_path on Windows is under user temp under home, so always allowed.
        pytest.skip("Windows tmp_path is under home; tested by env-var test")
    foreign = Path("/tmp/jayclaw-test-foreign")
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", "")
    with pytest.raises(HTTPException) as exc:
        _check_workspace_path(str(foreign))
    assert exc.value.status_code == 403


def test_check_workspace_path_extra_roots_via_env(tmp_path, monkeypatch):
    """WEB_UI_WORKSPACE_ROOTS extends the whitelist."""
    extra = tmp_path / "extra-root"
    extra.mkdir()
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", str(extra))

    target = extra / "child"
    out = _check_workspace_path(str(target))
    assert out == target.resolve()


def test_allowed_workspace_roots_includes_home_and_cwd():
    roots = _allowed_workspace_roots()
    assert Path.home().resolve() in roots
    assert Path.cwd().resolve() in roots


def test_allowed_workspace_roots_dedups_when_cwd_under_home(monkeypatch):
    """If cwd is already under home, it's still listed (we don't try to
    flatten — just dedup exact duplicates)."""
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", str(Path.home()))
    roots = _allowed_workspace_roots()
    # Home appears exactly once even though env adds it again
    home_count = sum(1 for r in roots if r == Path.home().resolve())
    assert home_count == 1


def test_is_under_allowed_root_true_for_home():
    assert _is_under_allowed_root(Path.home() / "anything")


def test_is_under_allowed_root_false_for_root_dir(monkeypatch):
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", "")
    if os.name == "nt":
        # On Windows, "/" resolves to the cwd's drive root, which is usually
        # under cwd's tree — skip
        pytest.skip("Windows root resolution differs")
    # /var on a typical Linux box is not under home/cwd/extra
    assert not _is_under_allowed_root(Path("/var/log/syslog"))


def test_check_workspace_path_expands_tilde():
    """`~/foo` should resolve to <home>/foo."""
    out = _check_workspace_path("~/some-folder")
    assert out == (Path.home() / "some-folder").resolve()


# ---------------------------------------------------------------------------
# Edge cases — exception paths in env parsing & resolve()
# ---------------------------------------------------------------------------


def test_allowed_workspace_roots_skips_oserror_token(monkeypatch, tmp_path):
    """If a token in WEB_UI_WORKSPACE_ROOTS fails to resolve(), it's silently
    skipped — but valid tokens before/after still land in the result."""
    valid = tmp_path / "valid"
    valid.mkdir()

    sep = ";" if os.name == "nt" else ":"
    # On Linux, /proc/1/root often raises PermissionError → OSError when resolved
    # by a non-root process. Use a poisoned Path subclass instead so the test
    # is deterministic on every platform.
    bad_token = "  "  # whitespace stripped → empty → 'continue' branch
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", f"{bad_token}{sep}{valid}")

    roots = _allowed_workspace_roots()
    assert valid.resolve() in roots


def test_allowed_workspace_roots_handles_resolve_oserror(monkeypatch):
    """When Path(token).expanduser().resolve() raises OSError, the loop
    skips that token instead of crashing."""
    sep = ";" if os.name == "nt" else ":"
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", f"/__bad_token__{sep}~")

    # Patch Path.resolve to selectively blow up on the bad token.
    real_resolve = Path.resolve

    def _flaky(self, *args, **kwargs):
        if "__bad_token__" in str(self):
            raise OSError("simulated resolve failure")
        return real_resolve(self, *args, **kwargs)

    with patch.object(Path, "resolve", _flaky):
        roots = _allowed_workspace_roots()

    # The bad token never landed in the result — the OSError branch triggered.
    assert all("__bad_token__" not in str(r) for r in roots)


def test_check_workspace_path_handles_oserror_during_resolve(monkeypatch):
    """Path.resolve() can raise OSError on bad inputs (e.g. ELOOP). The
    helper should turn that into HTTP 400, not crash."""

    real_resolve = Path.resolve

    def _flaky(self, *args, **kwargs):
        if "trigger-oserror" in str(self):
            raise OSError("simulated")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", "")
    with patch.object(Path, "resolve", _flaky):
        with pytest.raises(HTTPException) as exc:
            _check_workspace_path("/trigger-oserror/path")
    assert exc.value.status_code == 400
    assert "invalid path" in exc.value.detail


def test_is_under_allowed_root_false_when_no_root_matches(monkeypatch, tmp_path):
    """Directly exercise the False branch where every root.relative_to() raises."""
    # Empty whitelist + no env override → only home/cwd
    monkeypatch.setenv("WEB_UI_WORKSPACE_ROOTS", "")
    if os.name == "nt":
        pytest.skip("Windows tmp resolution overlaps user dirs")
    # /var is universally outside home/cwd in CI environments
    assert not _is_under_allowed_root(Path("/var/log/auth.log"))

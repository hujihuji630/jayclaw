"""Path-validation primitives shared by the HTTP route modules.

Two layers of defence live here:

* ``_check_workspace_path`` — used by ``/api/workspace`` and ``/api/browse*``
  to confirm a client-supplied directory is inside the operator-blessed
  whitelist (home / cwd / ``$WEB_UI_WORKSPACE_ROOTS``) and not a known-sensitive
  system path.
* ``_safe_join`` — used by ``/api/upload`` and ``/api/files (DELETE)`` to clamp
  an untrusted basename underneath a trusted directory, defeating
  ``..``/absolute-path traversal.

These helpers raise ``HTTPException`` and are the single point of truth tested
in [test_workspace_whitelist.py] and [test_safe_join.py].
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from fastapi import HTTPException


# Always blocked (case-insensitive prefix match), even if otherwise allowed:
SYSTEM_PATH_DENY_PREFIXES = (
    # Unix
    "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
    "/sys", "/proc", "/dev", "/boot", "/root",
    # Windows
    "c:\\windows", "c:\\program files", "c:\\program files (x86)",
    "c:\\programdata",
)


def _allowed_workspace_roots() -> list[Path]:
    roots: list[Path] = [Path.home().resolve()]
    try:
        roots.append(Path.cwd().resolve())
    except OSError:
        pass
    # On Windows, allow all fixed drive roots (sensitive paths are blocked by deny-list)
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                roots.append(drive)
    extra = os.environ.get("WEB_UI_WORKSPACE_ROOTS", "").strip()
    if extra:
        sep = ";" if os.name == "nt" else ":"
        for token in extra.split(sep):
            token = token.strip()
            if not token:
                continue
            try:
                roots.append(Path(token).expanduser().resolve())
            except OSError:
                continue
    seen: set[str] = set()
    deduped: list[Path] = []
    for r in roots:
        key = str(r).lower() if os.name == "nt" else str(r)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def _is_system_path(p: Path) -> bool:
    """Return True if ``p`` falls under a known-sensitive system prefix.

    Normalizes ``/`` and ``\\`` so /etc on Linux and C:\\Windows on Windows
    are checked uniformly across platforms.
    """
    s = str(p).lower().replace("\\", "/")
    for raw_prefix in SYSTEM_PATH_DENY_PREFIXES:
        prefix = raw_prefix.replace("\\", "/")
        if s == prefix or s.startswith(prefix + "/"):
            return True
    return False


def _is_under_allowed_root(target: Path) -> bool:
    target = target.resolve()
    for root in _allowed_workspace_roots():
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _check_workspace_path(raw: str) -> Path:
    """Resolve and validate a workspace path supplied by an HTTP client."""
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="path is required")
    if "\x00" in raw:
        raise HTTPException(status_code=400, detail="path contains NUL byte")
    try:
        candidate = Path(raw).expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"invalid path: {exc}") from exc

    if _is_system_path(candidate):
        raise HTTPException(status_code=403, detail="system paths are not allowed")
    if not _is_under_allowed_root(candidate):
        raise HTTPException(
            status_code=403,
            detail=(
                "path is outside allowed roots (~ / cwd / $WEB_UI_WORKSPACE_ROOTS); "
                "set WEB_UI_WORKSPACE_ROOTS to extend the whitelist"
            ),
        )
    return candidate


def _safe_join(base: Path, untrusted: str) -> Path:
    """Join ``untrusted`` onto ``base`` and verify the result stays inside ``base``.

    Strips client-supplied directory components, resolves symlinks, then asserts
    the final path is contained in ``base``. Raises HTTPException(400) on escape.

    Rejected as 400:
    - empty / ``.`` / ``..`` / whitespace-only basenames
    - filenames containing NUL bytes (path-truncation attack on some OSes)
    - any input whose resolved path falls outside ``base``
    """
    if not untrusted:
        raise HTTPException(status_code=400, detail="filename is required")
    if "\x00" in untrusted:
        raise HTTPException(status_code=400, detail="filename contains NUL byte")

    name = PurePosixPath(untrusted.replace("\\", "/")).name
    if not name or not name.strip() or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid filename")

    candidate = (base / name).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes base directory") from exc
    return candidate

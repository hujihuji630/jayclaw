"""CLI command verification."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .base import CheckResult, CheckStatus


async def cli_check(
    command: str,
    *,
    cwd: str | Path | None = None,
    expected_exit_code: int = 0,
    stdout_contains: str | None = None,
    stdout_not_contains: str | None = None,
    timeout: float = 30.0,
) -> CheckResult:
    """Run a CLI command and verify its output."""
    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"cli: {command[:40]}",
            status=CheckStatus.FAIL,
            message=f"Timed out after {timeout}s",
            duration_ms=duration,
        )
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"cli: {command[:40]}",
            status=CheckStatus.FAIL,
            message=f"Execution error: {e}",
            duration_ms=duration,
        )

    duration = (time.perf_counter() - start) * 1000
    stdout_str = stdout_bytes.decode(errors="replace")
    name = f"cli: {command[:40]}"

    if proc.returncode != expected_exit_code:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"Exit code {proc.returncode} (expected {expected_exit_code})",
            detail=stderr_bytes.decode(errors="replace")[:200],
            duration_ms=duration,
        )

    if stdout_contains and stdout_contains not in stdout_str:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"stdout missing: '{stdout_contains}'",
            duration_ms=duration,
        )

    if stdout_not_contains and stdout_not_contains in stdout_str:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"stdout unexpectedly contains: '{stdout_not_contains}'",
            duration_ms=duration,
        )

    return CheckResult(
        name=name,
        status=CheckStatus.PASS,
        message="Command succeeded",
        duration_ms=duration,
    )

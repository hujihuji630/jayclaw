"""HTTP endpoint verification."""

from __future__ import annotations

import time

from .base import CheckResult, CheckStatus


async def http_check(
    url: str,
    *,
    method: str = "GET",
    expected_status: int = 200,
    body_contains: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> CheckResult:
    """Send HTTP request and verify response."""
    try:
        import httpx
    except ImportError:
        return CheckResult(
            name=f"http: {method} {url[:30]}",
            status=CheckStatus.SKIP,
            message="httpx not installed",
        )

    start = time.perf_counter()
    name = f"http: {method} {url[:30]}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers)
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"Request failed: {e}",
            duration_ms=duration,
        )

    duration = (time.perf_counter() - start) * 1000

    if resp.status_code != expected_status:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"Status {resp.status_code} (expected {expected_status})",
            detail=resp.text[:200],
            duration_ms=duration,
        )

    if body_contains and body_contains not in resp.text:
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"Body missing: '{body_contains}'",
            duration_ms=duration,
        )

    return CheckResult(
        name=name,
        status=CheckStatus.PASS,
        message=f"Status {resp.status_code} OK",
        duration_ms=duration,
    )

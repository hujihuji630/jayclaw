"""Browser-based verification using Playwright (optional dependency)."""

from __future__ import annotations

import time

from .base import CheckResult, CheckStatus


async def browser_check(
    url: str,
    *,
    wait_for_selector: str | None = None,
    text_contains: str | None = None,
    timeout: float = 15000,
) -> CheckResult:
    """Open URL in headless browser and verify content.

    Returns CheckResult (SKIP if playwright not installed).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return CheckResult(
            name=f"browser: {url[:30]}",
            status=CheckStatus.SKIP,
            message="playwright not installed (pip install playwright && playwright install)",
        )

    start = time.perf_counter()
    name = f"browser: {url[:30]}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=timeout)

            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=timeout)

            if text_contains:
                content = await page.content()
                if text_contains not in content:
                    await browser.close()
                    duration = (time.perf_counter() - start) * 1000
                    return CheckResult(
                        name=name,
                        status=CheckStatus.FAIL,
                        message=f"Page missing text: '{text_contains}'",
                        duration_ms=duration,
                    )

            await browser.close()
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"Browser error: {e}",
            duration_ms=duration,
        )

    duration = (time.perf_counter() - start) * 1000
    return CheckResult(
        name=name,
        status=CheckStatus.PASS,
        message="Page loaded and verified",
        duration_ms=duration,
    )

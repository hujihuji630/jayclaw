"""Free web search providers: Bing CN, Baidu, DuckDuckGo (no API key required)."""

from .base import SearchResult


class BingCNProvider:
    """Free web search using Bing China (cn.bing.com). Works well in mainland China."""

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise RuntimeError("Install with: pip install httpx beautifulsoup4") from e

        url = f"https://cn.bing.com/search?q={query}&setlang=zh-CN&mkt=zh-CN"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP error {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError("Search request timed out") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}") from e

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for li in soup.select("li.b_algo")[:max_results]:
            title_el = li.select_one("h2 a")
            snippet_el = li.select_one("p, .b_caption p")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title and href:
                results.append(SearchResult(title=title, url=href, snippet=snippet, score=1.0))

        return results


class BaiduProvider:
    """Free web search using Baidu. Fallback for when Bing CN is unavailable."""

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise RuntimeError("Install with: pip install httpx beautifulsoup4") from e

        url = f"https://www.baidu.com/s?wd={query}&rn={max_results}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP error {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError("Search request timed out") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}") from e

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for div in soup.select("div.result, div.c-container")[:max_results]:
            title_el = div.select_one("h3 a, .t a")
            snippet_el = div.select_one(".c-abstract, .content-right_8Zs40")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title and href:
                results.append(SearchResult(title=title, url=href, snippet=snippet, score=0.9))

        return results


class DuckDuckGoProvider:
    """Free web search using DuckDuckGo HTML interface. May be slow in mainland China."""

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise RuntimeError("Install with: pip install httpx beautifulsoup4") from e

        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.post(url, data={"q": query}, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP error {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError("Search request timed out") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}") from e

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result_div in soup.select("div.result")[:max_results]:
            title_el = result_div.select_one("a.result__a")
            snippet_el = result_div.select_one("a.result__snippet")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title and href:
                results.append(SearchResult(title=title, url=href, snippet=snippet, score=1.0))

        return results


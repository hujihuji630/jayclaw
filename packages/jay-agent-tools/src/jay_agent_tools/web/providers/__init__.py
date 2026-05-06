"""Web tool provider implementations."""

from .base import PageContent, ReaderProvider, SearchProvider, SearchResult
from .duckduckgo import BaiduProvider, BingCNProvider, DuckDuckGoProvider
from .exa import ExaProvider
from .httpx_bs4 import HttpxBs4Provider
from .jina import JinaReaderProvider
from .tavily import TavilyProvider


class FallbackSearchProvider:
    """Tries multiple providers in order, returns first successful result."""

    def __init__(self, providers: list):
        self._providers = providers

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        last_error = None
        for provider in self._providers:
            try:
                results = await provider.search(query, max_results=max_results)
                if results:
                    return results
            except Exception as e:
                last_error = e
                continue
        if last_error:
            raise RuntimeError(f"All search providers failed. Last error: {last_error}")
        return []


def get_default_provider() -> "SearchProvider":
    """Auto-detect and return the best available search provider.

    Priority order:
    1. TAVILY_API_KEY  → TavilyProvider (paid, best quality)
    2. EXA_API_KEY     → ExaProvider (paid)
    3. (fallback)      → BingCN → Baidu chain (free, works in China)
    """
    import os

    if os.getenv("TAVILY_API_KEY"):
        return TavilyProvider()
    if os.getenv("EXA_API_KEY"):
        return ExaProvider()
    return FallbackSearchProvider([BingCNProvider(), BaiduProvider()])


def get_default_reader() -> "ReaderProvider":
    """Return the default reader provider (JinaReaderProvider)."""
    return JinaReaderProvider()


__all__ = [
    "SearchProvider", "SearchResult", "ReaderProvider", "PageContent",
    "TavilyProvider", "ExaProvider",
    "BingCNProvider", "BaiduProvider", "DuckDuckGoProvider",
    "FallbackSearchProvider",
    "JinaReaderProvider", "HttpxBs4Provider",
    "get_default_provider", "get_default_reader",
]


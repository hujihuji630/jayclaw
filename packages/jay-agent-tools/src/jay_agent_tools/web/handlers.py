"""Web tool handlers."""

from typing import Any

from jay_agent_core.tools.base import ToolResult

from .providers.base import ReaderProvider, SearchProvider


async def handle_search_web(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
    provider: SearchProvider | None = None,
) -> ToolResult:
    """Search the web and return formatted results."""
    query = args.get("query", "")
    max_results = args.get("max_results", 5)

    if not query:
        return ToolResult(ok=False, error="Query parameter is required")

    try:
        if provider is None:
            from .providers import get_default_provider
            provider = get_default_provider()

        results = await provider.search(query, max_results=max_results)

        if not results:
            return ToolResult(ok=True, data="No results found")

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}\n   URL: {r.url}\n   {r.snippet}\n")

        return ToolResult(ok=True, data="\n".join(lines))

    except RuntimeError as e:
        return ToolResult(ok=False, error=str(e))
    except Exception as e:
        return ToolResult(ok=False, error=f"Search failed: {e}")


async def handle_read_webpage(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
    reader: ReaderProvider | None = None,
) -> ToolResult:
    """Fetch a webpage and return its text content.

    The ``reader`` argument selects the extraction backend:

    - ``JinaReaderProvider`` (default) — routes through Jina Reader API,
      returns clean Markdown, handles JS-rendered pages, free without a key.
    - ``HttpxBs4Provider`` — fetches raw HTML locally, strips boilerplate
      with BeautifulSoup.  No external API, but cannot run JS.

    Args:
        args: Tool arguments — ``url`` (required).
        user_id: Optional user identifier passed by the agent runtime.
        meta: Optional metadata passed by the agent runtime.
        cancel: Optional cancellation token passed by the agent runtime.
        reader: Explicit reader provider instance.

    Returns:
        ToolResult with extracted page text on success.
    """
    url = args.get("url", "")

    if not url:
        return ToolResult(ok=False, error="URL parameter is required")

    if not url.startswith(("http://", "https://")):
        return ToolResult(ok=False, error="URL must start with http:// or https://")

    try:
        if reader is None:
            from .providers.jina import JinaReaderProvider

            reader = JinaReaderProvider()

        page = await reader.read(url)
        return ToolResult(ok=True, data=page.content)

    except RuntimeError as e:
        return ToolResult(ok=False, error=str(e))
    except Exception as e:
        return ToolResult(ok=False, error=f"Failed to read webpage: {e}")


# Common pinyin tokens found in Chinese developer codebases
_PINYIN_WORDS = {
    # User / auth
    "yonghu", "yonghuid", "yonghuming", "mima", "denglu", "zhuce",
    "quanxian", "jiaose", "yanzheng",
    # Data structures
    "shuju", "liebiao", "shuzu", "duixiang", "zidian", "jiegou", "moxing",
    "shujuku", "biao", "hang", "lie",
    # Common actions
    "chaxun", "tianjia", "shanchu", "xiugai", "gengxin", "huoqu", "baocun",
    "chuangjian", "jiancha", "chuli", "fanhuizhi", "canshu", "jieguo",
    # System / infra
    "peizhi", "rizhi", "cuowu", "yichang", "xinxi", "zhuangtai",
    "fuwuqi", "duankou", "lujing", "wenjian", "mulu", "jiekou",
    # Business
    "dingdan", "shangpin", "jiage", "shuliang", "zongji", "fenlei",
    "pinglun", "pingjia", "biaoqian", "tupian", "neirong", "biaoti",
    # Time
    "shijian", "riqi", "chuangjianshijian", "gengxinshijian",
    # Misc
    "hanshu", "fangfa", "leixing", "mingcheng", "bianma", "geshu",
    "suoyin", "zhishu",
}

_SUGGESTIONS: dict[str, str] = {
    "yonghu": "user", "mima": "password", "denglu": "login", "zhuce": "register",
    "quanxian": "permission", "jiaose": "role", "yanzheng": "verify",
    "shuju": "data", "liebiao": "list", "shuzu": "array", "duixiang": "object",
    "zidian": "dict", "jiegou": "struct", "moxing": "model",
    "shujuku": "database", "biao": "table", "hang": "row", "lie": "column",
    "chaxun": "query", "tianjia": "add", "shanchu": "delete", "xiugai": "modify",
    "gengxin": "update", "huoqu": "get", "baocun": "save", "chuangjian": "create",
    "jiancha": "check", "chuli": "process", "fanhuizhi": "return_value",
    "canshu": "param", "jieguo": "result",
    "peizhi": "config", "rizhi": "log", "cuowu": "error", "yichang": "exception",
    "xinxi": "info", "zhuangtai": "status", "fuwuqi": "server",
    "duankou": "port", "lujing": "path", "wenjian": "file", "mulu": "dir",
    "jiekou": "interface",
    "dingdan": "order", "shangpin": "product", "jiage": "price",
    "shuliang": "quantity", "zongji": "total", "fenlei": "category",
    "pinglun": "comment", "pingjia": "rating", "biaoqian": "tag",
    "tupian": "image", "neirong": "content", "biaoti": "title",
    "shijian": "time", "riqi": "date",
    "hanshu": "func", "fangfa": "method", "leixing": "type",
    "mingcheng": "name", "bianma": "code", "geshu": "count", "suoyin": "index",
}


async def handle_search_zhihu(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
) -> ToolResult:
    """搜索网络内容，优先使用通用搜索引擎，失败时尝试知乎。

    Args:
        args: Tool arguments — ``query`` (required).
        user_id: Optional user identifier.
        meta: Optional metadata.
        cancel: Optional cancellation token.

    Returns:
        ToolResult with formatted search results.
    """
    query = args.get("query", "").strip()
    if not query:
        return ToolResult(ok=False, error="query 参数不能为空")

    # 优先使用通用搜索引擎（Bing CN → Baidu → DuckDuckGo）
    try:
        from .providers import get_default_provider

        provider = get_default_provider()
        results = await provider.search(query, max_results=5)

        if results:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}\n")
            return ToolResult(ok=True, data="\n".join(lines))
    except Exception:
        pass

    # Fallback 1: 百度搜索
    try:
        from .providers.duckduckgo import BaiduProvider

        results = await BaiduProvider().search(query, max_results=5)
        if results:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}\n")
            return ToolResult(ok=True, data="\n".join(lines))
    except Exception:
        pass

    # Fallback: 知乎搜索
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        return ToolResult(
            ok=False,
            error="缺少依赖，请安装: pip install httpx beautifulsoup4",
        )

    url = f"https://www.zhihu.com/search?type=content&q={query}"
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
    except Exception as e:
        return ToolResult(
            ok=True,
            data=f"搜索「{query}」时遇到网络问题。建议直接访问搜索引擎查看结果。",
        )

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    cards = soup.select("div.SearchResult-Card")[:5]

    for card in cards:
        title_el = card.select_one("h2.ContentItem-title a, .Title a")
        excerpt_el = card.select_one(".RichText, .ContentItem-summary")
        if title_el:
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href.startswith("/"):
                href = "https://www.zhihu.com" + href
            excerpt = excerpt_el.get_text(strip=True)[:200] if excerpt_el else ""
            results.append(f"- {title}\n  {href}\n  {excerpt}")

    if not results:
        links = soup.select("a[href*='/question/'], a[href*='/answer/']")[:5]
        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href.startswith("/"):
                href = "https://www.zhihu.com" + href
            if title:
                results.append(f"- {title}\n  {href}")

    if not results:
        return ToolResult(
            ok=True,
            data=f"未找到关于「{query}」的结果。建议直接访问搜索引擎查看。",
        )

    output = f"搜索「{query}」结果：\n\n" + "\n\n".join(results)
    return ToolResult(ok=True, data=output)


async def handle_translate_to_english(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
) -> ToolResult:
    """将中文文本翻译为英文，使用 MyMemory 免费翻译 API。

    Args:
        args: Tool arguments — ``text`` (required).
        user_id: Optional user identifier.
        meta: Optional metadata.
        cancel: Optional cancellation token.

    Returns:
        ToolResult with translated English text.
    """
    text = args.get("text", "").strip()
    if not text:
        return ToolResult(ok=False, error="text 参数不能为空")

    if len(text) > 500:
        return ToolResult(ok=False, error="文本过长，请控制在500字以内")

    try:
        import httpx
    except ImportError:
        return ToolResult(ok=False, error="缺少依赖，请安装: pip install httpx")

    api_url = "https://api.mymemory.translated.net/get"
    params = {"q": text, "langpair": "zh|en"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return ToolResult(ok=False, error="翻译请求超时")
    except httpx.RequestError as e:
        return ToolResult(ok=False, error=f"网络错误: {e}")
    except Exception as e:
        return ToolResult(ok=False, error=f"翻译失败: {e}")

    translated = data.get("responseData", {}).get("translatedText", "")
    if not translated:
        return ToolResult(ok=False, error="翻译结果为空，请稍后重试")

    output = f"原文: {text}\n译文: {translated}"
    return ToolResult(ok=True, data=output)


async def handle_check_pinyin_naming(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
) -> ToolResult:
    """检测代码中的拼音变量名并给出英文命名建议。

    Args:
        args: Tool arguments — ``code`` (required), ``language`` (optional).
        user_id: Optional user identifier.
        meta: Optional metadata.
        cancel: Optional cancellation token.

    Returns:
        ToolResult with list of pinyin identifiers and suggestions.
    """
    import re

    code = args.get("code", "").strip()
    if not code:
        return ToolResult(ok=False, error="code 参数不能为空")

    # Extract identifier tokens
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", code)
    seen: set[str] = set()
    findings: list[str] = []

    for token in tokens:
        if token in seen or len(token) < 3:
            continue
        seen.add(token)

        # Split identifier into parts
        if "_" in token:
            parts = [p.lower() for p in token.split("_") if p]
        else:
            parts = re.sub(r"([A-Z])", r"_\1", token).strip("_").split("_")
            parts = [p.lower() for p in parts if p]

        matched_parts = [p for p in parts if p in _PINYIN_WORDS]
        if matched_parts:
            suggestions = [_SUGGESTIONS.get(p, f"<{p}_en>") for p in matched_parts]
            suggested_name = "_".join(suggestions) if "_" in token else "".join(
                s.capitalize() if i > 0 else s for i, s in enumerate(suggestions)
            )
            findings.append(
                f"  {token!r:30s} → 建议改为: {suggested_name!r}  "
                f"(匹配拼音: {', '.join(matched_parts)})"
            )

    if not findings:
        return ToolResult(ok=True, data="未检测到拼音命名，代码命名规范！")

    header = f"检测到 {len(findings)} 个疑似拼音命名：\n"
    body = "\n".join(findings)
    footer = "\n\n提示：使用英文命名可提升代码可读性和国际化水平。"
    return ToolResult(ok=True, data=header + body + footer)


HANDLERS = {
    "search_web": handle_search_web,
    "read_webpage": handle_read_webpage,
    "search_zhihu": handle_search_zhihu,
    "translate_to_english": handle_translate_to_english,
    "check_pinyin_naming": handle_check_pinyin_naming,
}

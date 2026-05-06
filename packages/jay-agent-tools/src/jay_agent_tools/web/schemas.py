"""Tool schemas for web tools."""

from typing import Any


def _fn(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Helper to build OpenAI function calling schema.

    Args:
        name: Function name
        description: Function description
        parameters: Parameters schema

    Returns:
        OpenAI function calling schema
    """
    return {
        "type": "function",
        "_permission": "read",  # Web tools are read-only
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
            "strict": True,
        },
    }


# Search web tool schema
SEARCH_WEB_SCHEMA = _fn(
    name="search_web",
    description=(
        "Search the web for information using Tavily API. "
        "Returns a list of search results with titles, URLs, and snippets."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)

# Read webpage tool schema
READ_WEBPAGE_SCHEMA = _fn(
    name="read_webpage",
    description=(
        "Read and extract text content from a webpage. Returns the main text content of the page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to read",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
)

# Search Zhihu tool schema
SEARCH_ZHIHU_SCHEMA = _fn(
    name="search_zhihu",
    description=(
        "搜索知乎技术问答，返回最多5条结果，包含标题、摘要和链接。"
        "适合查找中文技术解答和经验分享。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词（支持中文）",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)

# Translate to English tool schema
TRANSLATE_TO_ENGLISH_SCHEMA = _fn(
    name="translate_to_english",
    description=(
        "将中文文本翻译成英文，使用免费翻译API，无需API密钥。"
        "适合将中文代码注释、变量名含义翻译为英文。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "需要翻译的中文文本（500字以内）",
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)

# Check pinyin naming tool schema
CHECK_PINYIN_NAMING_SCHEMA = _fn(
    name="check_pinyin_naming",
    description=(
        "检测代码中的拼音变量名，给出英文命名建议，提升代码国际化质量。"
        "支持 camelCase 和 snake_case 命名风格。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "需要检测的代码字符串",
            },
            "language": {
                "type": "string",
                "description": "编程语言（python/javascript/java/go），默认 python",
                "default": "python",
            },
        },
        "required": ["code"],
        "additionalProperties": False,
    },
)

# All web tool schemas
TOOL_SCHEMAS = [
    SEARCH_WEB_SCHEMA,
    READ_WEBPAGE_SCHEMA,
    SEARCH_ZHIHU_SCHEMA,
    TRANSLATE_TO_ENGLISH_SCHEMA,
    CHECK_PINYIN_NAMING_SCHEMA,
]

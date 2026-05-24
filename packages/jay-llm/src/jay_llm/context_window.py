"""Resolve the context window (max input tokens) for a given model.

Resolution order:
1. Explicit env override: ``LLM_CONTEXT_WINDOW``
2. ``litellm.get_model_info()`` if litellm is installed (community-maintained table)
3. Family prefix table (handles dated suffixes like ``gpt-4o-2024-08-06``)
4. Provider default
5. Hard fallback: 8192
"""

from __future__ import annotations

import os
from functools import lru_cache

# Family prefix -> context window. Order matters: longer/more-specific
# prefixes must come before shorter ones (the resolver picks the first match).
_FAMILY_WINDOWS: list[tuple[str, int]] = [
    # OpenAI
    ("gpt-4.1", 1_047_576),
    ("gpt-4o-mini", 128_000),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-4-32k", 32_768),
    ("gpt-4", 8_192),
    ("gpt-3.5-turbo-16k", 16_385),
    ("gpt-3.5-turbo", 16_385),
    ("o1-mini", 128_000),
    ("o1-preview", 128_000),
    ("o1", 200_000),
    ("o3-mini", 200_000),
    ("o3", 200_000),
    ("o4-mini", 200_000),
    # Anthropic Claude
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-haiku-4", 200_000),
    ("claude-3-7-sonnet", 200_000),
    ("claude-3-5-sonnet", 200_000),
    ("claude-3-5-haiku", 200_000),
    ("claude-3-opus", 200_000),
    ("claude-3-sonnet", 200_000),
    ("claude-3-haiku", 200_000),
    ("claude-2.1", 200_000),
    ("claude-2", 100_000),
    # Google Gemini
    ("gemini-2.5", 1_048_576),
    ("gemini-2.0", 1_048_576),
    ("gemini-1.5-pro", 2_097_152),
    ("gemini-1.5-flash", 1_048_576),
    ("gemini-1.0-pro", 32_768),
    ("gemini-pro", 32_768),
    # DeepSeek
    ("deepseek-reasoner", 65_536),
    ("deepseek-chat", 65_536),
    ("deepseek-coder", 16_384),
    # Mistral
    ("mistral-large", 128_000),
    ("mistral-medium", 32_768),
    ("mistral-small", 32_768),
    ("mistral-tiny", 32_768),
    ("mixtral-8x22b", 65_536),
    ("mixtral-8x7b", 32_768),
    ("codestral", 32_768),
    # Groq (hosts Llama/Mixtral)
    ("llama-3.3", 128_000),
    ("llama-3.2", 128_000),
    ("llama-3.1", 128_000),
    ("llama3", 8_192),
    # xAI Grok
    ("grok-2", 131_072),
    ("grok-beta", 131_072),
    ("grok", 8_192),
    # Cohere
    ("command-r-plus", 128_000),
    ("command-r", 128_000),
    ("command", 4_096),
    # Perplexity
    ("sonar", 127_072),
    # Zhipu GLM
    ("glm-4-plus", 128_000),
    ("glm-4", 128_000),
    # Qwen
    ("qwen2.5", 128_000),
    ("qwen2", 32_768),
    ("qwen", 8_192),
]

# Provider-level default if no family matches.
_PROVIDER_DEFAULTS: dict[str, int] = {
    "openai": 16_385,
    "anthropic": 200_000,
    "google": 1_048_576,
    "azure": 16_385,
    "groq": 8_192,
    "mistral": 32_768,
    "cohere": 4_096,
    "deepseek": 32_768,
    "perplexity": 32_768,
    "openrouter": 32_768,
    "together": 32_768,
    "cerebras": 8_192,
    "xai": 131_072,
    "bedrock": 200_000,
    "glm": 128_000,
}

_HARD_FALLBACK = 8_192


@lru_cache(maxsize=256)
def detect_context_window(model: str | None, provider: str | None = None) -> int:
    """Return the context window size (max input tokens) for a model.

    Args:
        model: Model identifier (e.g. ``gpt-4o``, ``claude-3-5-sonnet-20241022``).
        provider: Provider name (used only as a last-resort fallback).

    Returns:
        Context window size in tokens. Always returns a positive int.
    """
    env_override = os.environ.get("LLM_CONTEXT_WINDOW")
    if env_override:
        try:
            value = int(env_override)
            if value > 0:
                return value
        except ValueError:
            pass

    if model:
        if not isinstance(model, str):
            model = str(model)
        litellm_value = _try_litellm(model)
        if litellm_value:
            return litellm_value

        model_lc = model.lower()
        # Strip common provider prefixes like "openai/gpt-4o" or "anthropic/claude-3"
        if "/" in model_lc:
            model_lc = model_lc.split("/", 1)[1]

        for prefix, window in _FAMILY_WINDOWS:
            if model_lc.startswith(prefix):
                return window

    if provider:
        provider_lc = provider.lower()
        if provider_lc in _PROVIDER_DEFAULTS:
            return _PROVIDER_DEFAULTS[provider_lc]

    return _HARD_FALLBACK


def _try_litellm(model: str) -> int | None:
    """Best-effort lookup via litellm's community-maintained model table.

    Returns None if litellm is not installed or the model is unknown.
    """
    try:
        import litellm  # type: ignore
    except ImportError:
        return None

    try:
        info = litellm.get_model_info(model)
    except Exception:
        return None

    if not isinstance(info, dict):
        return None

    for key in ("max_input_tokens", "max_tokens"):
        value = info.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None

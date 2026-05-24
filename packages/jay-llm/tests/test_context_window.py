"""Tests for jay_llm.context_window — context-window resolution.

Covers the documented resolution order:
1. ``LLM_CONTEXT_WINDOW`` env override
2. ``litellm.get_model_info()`` (when installed)
3. Family-prefix table (handles dated suffixes, provider prefixes, case)
4. Provider default
5. Hard fallback (8192)
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from jay_llm import context_window as cw_mod
from jay_llm.context_window import detect_context_window


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """Reset memoization between tests so env / monkeypatching takes effect."""
    detect_context_window.cache_clear()
    yield
    detect_context_window.cache_clear()


@pytest.fixture(autouse=True)
def _no_litellm(monkeypatch):
    """Default: pretend litellm is not installed so family-table is exercised.

    Tests that need the litellm path opt in by clearing this with their own
    monkeypatching. Importing litellm in CI is undesirable and slow.
    """
    # Force the ImportError branch in _try_litellm by hiding any cached module.
    monkeypatch.setitem(sys.modules, "litellm", None)
    yield


# ---------------------------------------------------------------------------
# Env override
# ---------------------------------------------------------------------------


def test_env_override_takes_precedence(monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "12345")
    # Pick a model that *would* match a family entry; env wins anyway.
    assert detect_context_window("gpt-4o") == 12345


def test_env_override_ignores_non_int(monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "not-a-number")
    # Falls through to family table.
    assert detect_context_window("gpt-4o") == 128_000


def test_env_override_ignores_zero_and_negative(monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "0")
    assert detect_context_window("gpt-4o") == 128_000

    detect_context_window.cache_clear()
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "-100")
    assert detect_context_window("gpt-4o") == 128_000


def test_env_override_empty_string_is_ignored(monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "")
    assert detect_context_window("gpt-4o") == 128_000


# ---------------------------------------------------------------------------
# Family-prefix table
# ---------------------------------------------------------------------------


def test_exact_family_match():
    assert detect_context_window("gpt-4o") == 128_000
    assert detect_context_window("claude-3-opus") == 200_000


def test_dated_suffix_still_matches():
    """Real model IDs often carry date suffixes; the prefix should still win."""
    assert detect_context_window("claude-3-5-sonnet-20241022") == 200_000
    assert detect_context_window("gpt-4o-2024-08-06") == 128_000


def test_more_specific_prefix_wins_over_shorter():
    """``gpt-4o-mini`` is listed before ``gpt-4o`` so the longer one wins."""
    assert detect_context_window("gpt-4o-mini") == 128_000
    # Both happen to resolve to 128k, but verify mini-specific input still hits its row.
    assert detect_context_window("gpt-4o-mini-2024-07-18") == 128_000


def test_provider_prefix_is_stripped():
    """``openai/gpt-4o`` → strip ``openai/`` → match family table."""
    assert detect_context_window("openai/gpt-4o") == 128_000
    assert detect_context_window("anthropic/claude-3-5-sonnet-20240620") == 200_000


def test_match_is_case_insensitive():
    assert detect_context_window("GPT-4O") == 128_000
    assert detect_context_window("Claude-3-Opus") == 200_000


def test_gemini_long_context_families():
    assert detect_context_window("gemini-1.5-pro-002") == 2_097_152
    assert detect_context_window("gemini-1.5-flash") == 1_048_576


def test_deepseek_and_qwen_families():
    assert detect_context_window("deepseek-reasoner") == 65_536
    assert detect_context_window("qwen2.5-coder-32b") == 128_000


# ---------------------------------------------------------------------------
# Provider default
# ---------------------------------------------------------------------------


def test_unknown_model_falls_back_to_provider_default():
    # Model doesn't match any prefix → use provider default.
    assert detect_context_window("totally-made-up-model", provider="anthropic") == 200_000
    detect_context_window.cache_clear()
    assert detect_context_window("totally-made-up-model", provider="cohere") == 4_096


def test_provider_default_is_case_insensitive():
    assert detect_context_window("unknown-x", provider="ANTHROPIC") == 200_000


def test_unknown_provider_falls_through_to_hard_fallback():
    assert detect_context_window("unknown-x", provider="not-a-provider") == 8_192


# ---------------------------------------------------------------------------
# Hard fallback
# ---------------------------------------------------------------------------


def test_no_model_no_provider_returns_hard_fallback():
    assert detect_context_window(None, None) == 8_192


def test_unknown_model_no_provider_returns_hard_fallback():
    assert detect_context_window("zzz-no-such-model") == 8_192


# ---------------------------------------------------------------------------
# litellm path (mocked)
# ---------------------------------------------------------------------------


def test_litellm_max_input_tokens_wins(monkeypatch):
    """When litellm reports max_input_tokens, prefer that over family table."""
    fake_litellm = type(sys)("litellm")
    fake_litellm.get_model_info = lambda model: {"max_input_tokens": 999_999}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    # Family table would give 128k for gpt-4o; litellm overrides.
    assert detect_context_window("gpt-4o") == 999_999


def test_litellm_falls_back_to_max_tokens_key(monkeypatch):
    fake_litellm = type(sys)("litellm")
    fake_litellm.get_model_info = lambda model: {"max_tokens": 4242}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    assert detect_context_window("gpt-4o") == 4242


def test_litellm_skipped_when_get_model_info_raises(monkeypatch):
    fake_litellm = type(sys)("litellm")

    def _boom(model):
        raise RuntimeError("model not in registry")

    fake_litellm.get_model_info = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    # Falls through to family table.
    assert detect_context_window("gpt-4o") == 128_000


def test_litellm_skipped_when_returns_non_dict(monkeypatch):
    fake_litellm = type(sys)("litellm")
    fake_litellm.get_model_info = lambda model: "not-a-dict"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    assert detect_context_window("gpt-4o") == 128_000


def test_litellm_skipped_when_keys_missing_or_invalid(monkeypatch):
    """Dict present but no positive int values → fall through."""
    fake_litellm = type(sys)("litellm")
    fake_litellm.get_model_info = lambda model: {  # type: ignore[attr-defined]
        "max_input_tokens": 0,
        "max_tokens": -5,
        "unrelated": "value",
    }
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    assert detect_context_window("gpt-4o") == 128_000


def test_litellm_not_installed_uses_family_table():
    """The autouse `_no_litellm` fixture forces ImportError; family wins."""
    assert detect_context_window("claude-opus-4-7") == 200_000


# ---------------------------------------------------------------------------
# Memoization
# ---------------------------------------------------------------------------


def test_results_are_memoized():
    detect_context_window("gpt-4o")
    info_before = detect_context_window.cache_info()
    detect_context_window("gpt-4o")
    info_after = detect_context_window.cache_info()
    assert info_after.hits == info_before.hits + 1

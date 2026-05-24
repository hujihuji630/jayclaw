# Changelog

All notable changes to JayClaw are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **Path traversal hardening for the Web UI**
  - `_safe_join` clamps untrusted basenames under a trusted parent for
    `/api/upload` and `DELETE /api/files`. Rejects empty / `.` / `..` /
    NUL-bearing / cross-directory inputs.
  - `_check_workspace_path` enforces a workspace whitelist (`~`, `cwd`,
    `$WEB_UI_WORKSPACE_ROOTS`) and refuses sensitive system paths
    (`/etc`, `C:\Windows`, …) on `/api/workspace` and `/api/browse*`.
- **Anti-DNS-rebinding `Host:` header middleware** — when the FastAPI app
  binds to `127.0.0.1` / `localhost` / `[::1]`, requests whose `Host:`
  doesn't match the listening address are rejected with HTTP 400. Disabled
  automatically when binding to a non-loopback address (operator opt-in).
- **CORS misconfiguration guard** — `cors_allow_origins` defaults to
  `f"http://{host}:{port}"` instead of `*`, preventing the dangerous
  wildcard + credentials combination.

### Added

- `jay_llm.context_window.detect_context_window()` resolves a model's input
  context window from a curated family-prefix table, with optional `litellm`
  override and `LLM_CONTEXT_WINDOW` env override.
- `jay_coding_agent.handoff` LLM-driven session handoff document generator
  with template fallback on LLM failure.
- `/api/handoff`, `/api/context`, `/api/agents-md/*` endpoints in the Web UI.
- Anthropic `astream` provider now correctly emits `tool_calls` deltas during
  streaming (previously dropped).

### Changed

- **`jay_web_ui.server` modularized.** The 1685-line monolithic
  `_setup_routes()` is split into focused submodules under
  `jay_web_ui.routes/` (`llm`, `lifecycle`, `files`, `workspace`,
  `sessions`, `agents_md`, `skills_tools`, `chat`). Path-validation
  primitives moved to `jay_web_ui.security`. Public `ChatServer` API and
  all HTTP routes are unchanged; existing imports from `jay_web_ui.server`
  (`_safe_join`, `_check_workspace_path`, …) still work.
- **Tool display labels are now schema-driven.** The hardcoded
  `_TOOL_LABELS = {"run_command": "执行命令", ...}` table inside the
  SSE handler is replaced by `jay_web_ui.tool_labels.build_tool_label_map`
  which derives a short label from each tool's schema `description`. New
  tools appear in the status line automatically; per-locale overrides live
  in one curated table for ease of translation.
- **Silent `except Exception: pass` blocks replaced with `logger.exception()`**
  (or `logger.warning(..., exc_info=True)` for expected fallback chains)
  across `attachments`, `agent`, `billing`, `bot`, `feishu`, web `handlers`,
  `tui/advanced`, and several Web UI route handlers — bugs are no longer
  invisibly swallowed.

### Docs

- Moved `HARNESS_*.md` development-journal documents from the repo root to
  `docs/dev-journal/` so the root tree stays clean for newcomers.

### Tests

- New `test_safe_join.py`, `test_workspace_whitelist.py`, `test_host_header.py`
  pin the Web UI's path/host security contract.
- `test_anthropic_astream.py` pins the streaming `tool_calls` reconstruction.
- `test_handoff.py` and `test_context_window.py` push both modules to **100%**
  line coverage.

## [0.1.0] — Initial release

- Multi-package monorepo: `jay-llm`, `jay-agent-core`, `jay-coding-agent`,
  `jay-messenger`, `jay-tui`, `jay-web-ui`.
- Provider adapters for OpenAI, Anthropic, Google, Azure, Bedrock, Cohere,
  DeepSeek, Groq, Mistral, OpenRouter, Perplexity, Together, xAI, Cerebras,
  GLM/Zhipu.
- Agent runtime with sessions, skills, tool registry, message queue,
  resilience chain, and observability hooks.
- Coding agent with file/git/web tools, AGENTS.md awareness, and
  workspace-switching support.
- Web UI with SSE streaming, attachments, vision-model fallback,
  workspace browser, AGENTS.md authoring, and handoff generation.

[Unreleased]: https://github.com/hujihuji630/jayclaw/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hujihuji630/jayclaw/releases/tag/v0.1.0

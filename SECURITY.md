# Security Policy

## Reporting a Vulnerability

If you believe you've found a security vulnerability in JayClaw, **do not open
a public GitHub issue**. Instead, report it privately via one of:

- GitHub Security Advisories: <https://github.com/hujihuji630/jayclaw/security/advisories/new>
- Email the maintainer (see commit log for current email)

Please include:

- A description of the vulnerability and potential impact
- Steps to reproduce (a minimal proof-of-concept is ideal)
- Affected version(s) and operating system
- Any mitigations you've already identified

We aim to acknowledge reports within **3 business days** and provide a fix or
mitigation timeline within **14 days**.

## Supported Versions

Only the `main` branch and the latest tagged release receive security fixes.
Older releases are not patched — please upgrade.

## Threat Model

JayClaw is an agent framework that ships:

- A **CLI** (`jay-coding-agent`) that runs on the developer's machine
- A **TUI** (`jay-tui`) that runs on the developer's machine
- A **Web UI** (`jay-web-ui`) that exposes a local FastAPI server
- A **messenger bridge** (`jay-messenger`) that connects to third-party chat
  platforms (Slack, Feishu, etc.)
- A **provider abstraction** (`jay-llm`) that calls hosted LLM APIs

The default deployment posture is **single-user, localhost-only**. The web UI
binds to `127.0.0.1` by default and refuses requests whose `Host:` header
doesn't match `127.0.0.1` / `localhost` / `[::1]` (DNS-rebinding guard). When
operators bind to `0.0.0.0` they are explicitly opting into broader exposure
and the guard is disabled.

## Hardening Already in Place

- **Path traversal** — `_safe_join` clamps every untrusted basename under a
  fixed parent directory (uploads, deletes). `_check_workspace_path` enforces
  a workspace whitelist (`~`, `cwd`, `$WEB_UI_WORKSPACE_ROOTS`) and refuses
  known-sensitive system paths (`/etc`, `C:\Windows`, etc.) for `/api/browse*`
  and `/api/workspace`.
- **Anti-DNS-rebinding** — `Host:` header validation on the localhost-bound
  FastAPI app rejects browser-driven requests that try to ride a rebound DNS
  name to your loopback service.
- **CORS** — never combines `*` origin with `allow_credentials=True`. When
  the operator enables CORS without explicit origins, the default is
  `f"http://{host}:{port}"` only.
- **Native dir picker** — `/api/browse/native` only runs when bound to
  loopback, and the user-picked path is re-validated against the same
  workspace whitelist as HTTP-supplied paths.
- **SSRF in LLM gateway** — outbound HTTP from `jay-llm` only goes to the
  provider's configured `base_url`; no user input is ever concatenated into
  the request URL.

## Out of Scope

- Vulnerabilities in third-party LLM providers themselves
- Issues that require local OS-level code execution (e.g. malicious skills
  added to `.claude/skills/` by the same user who owns the workspace)
- Denial of service via large-context model requests (rate-limited at the
  provider tier)

## Disclosure Policy

We follow coordinated disclosure: a security release will be tagged and
documented in [CHANGELOG.md](./CHANGELOG.md) once a fix is available, with
credit to the reporter unless they prefer to remain anonymous.

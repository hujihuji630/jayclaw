"""Per-workspace AGENTS.md generation and session-end summarization.

Two entry points:
- generate_initial(workspace, llm): scan workspace + LLM call → write AGENTS.md
- append_session_summary(workspace, llm, history): read existing AGENTS.md +
  conversation transcript → LLM extracts new pitfalls/constraints (JSON) →
  return (proposed_content, diff). Caller is responsible for asking the user
  to confirm before writing.

Inherits the three-section map style of jayclaw's own AGENTS.md
(Always Loaded / Knowledge Map / Known Pitfalls).
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


SKIP_DIRS = frozenset({
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "target",
    ".next",
    ".nuxt",
})


PROJECT_MARKERS: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "Gemfile": "ruby",
    "composer.json": "php",
    "mix.exs": "elixir",
}


INITIAL_TEMPLATE = """# AGENTS.md

> 这是一份 **地图**，不是百科全书。Agent 启动只读本文，按需展开细节。
> 总行数控制在 100 行以内；条目过期请及时移除。

## Always Loaded（硬约束，永远遵守）

{always_loaded}

## Knowledge Map（按需加载）

{knowledge_map}

## Known Pitfalls（历史教训，每条 1 行）

> 每次踩坑后追加一行。格式：`YYYY-MM: 简述`

_(empty — 会话结束后由 /agents-summarize 写入)_

## How to Use This Map

- Agent 启动时本文件自动注入到 system prompt
- 维护：会话结束时 Agent 会询问是否将经验追加到本文件
- 在 REPL 中可用 `/agents-init` 重新生成、`/agents-summarize` 立即追加
"""


DEFAULT_ALWAYS_LOADED = [
    "不要 commit `.env`、API key、`*.pem`、`*.key`、`credentials.json`",
    "破坏性操作（删文件、`git reset --hard`、`force push`）必须先与用户确认",
    "修改前先读相关文件；不要凭命名猜测 API 形态",
]


DEFAULT_KNOWLEDGE_MAP = "_(empty — 项目尚无沉淀的非平凡设计)_"


INIT_SYSTEM_PROMPT = """You are a senior engineer writing the *first* version of AGENTS.md for a freshly-discovered project, based on a workspace scan.

The user will give you a workspace snapshot (project type, top-level files, README excerpt, key config files). Your job: produce a **map-style** AGENTS.md — a short, skimmable index, NOT a manual.

Output a JSON object with exactly two keys:

```
{
  "always_loaded": ["constraint 1", "constraint 2", ...],
  "knowledge_map": ["- **topic-id** — when to read it", ...]
}
```

Rules for `always_loaded`:
- 3 to 7 entries, each one short imperative line
- Cover: secrets/credentials hygiene, destructive-action confirmation, project-specific build/test commands if obvious from the snapshot, language-specific gotchas if the project type is clear
- Do NOT invent constraints not supported by the snapshot
- Reuse the user's language (Chinese if the README/comments are Chinese; English otherwise)

Rules for `knowledge_map`:
- 0 to 8 entries
- Each entry format: `- **topic-id** — when to read it`
- Topic IDs are short kebab-case (e.g. `auth-flow`, `db-schema`, `build-pipeline`)
- Only include topics that the snapshot makes plausible — for an empty/trivial repo, return an empty list
- Do NOT invent file paths or modules that aren't visible in the snapshot

Output JSON only. No prose, no code fences."""


SUMMARY_SYSTEM_PROMPT = """You are a senior engineer extracting durable lessons from a coding-agent session, to append to the project's AGENTS.md.

The user will give you:
1. The current AGENTS.md content
2. The session transcript

Your job: identify *new* (not already in AGENTS.md) **pitfalls** the agent fell into and **constraints** the user explicitly stated. Be conservative — if a session was uneventful, return empty arrays.

Output a JSON object with exactly two keys:

```
{
  "new_pitfalls": ["short summary of what went wrong and why", ...],
  "new_constraints": ["short imperative constraint", ...]
}
```

Rules for `new_pitfalls`:
- One entry per genuine mistake-and-correction (the agent did X, the user said don't, here's the lesson)
- Format: imperative summary, ≤ 20 words. The date will be prepended automatically.
- Skip trivial typos or one-off bugs that are unlikely to recur
- Skip lessons already covered in the existing Known Pitfalls section

Rules for `new_constraints`:
- One entry per durable rule the user expressed (e.g. "always X", "never Y", "use Z library")
- Skip preferences that only apply to one specific task
- Skip constraints already in the existing Always Loaded section

If the session yielded no durable lessons, return both arrays empty. Do NOT pad.

Reuse the language of the existing AGENTS.md. Output JSON only — no prose, no code fences."""


@dataclass
class WorkspaceSnapshot:
    """Lightweight workspace fingerprint for the LLM."""

    project_type: str = "unknown"
    project_name: str = ""
    top_level: list[str] = field(default_factory=list)
    config_files: dict[str, str] = field(default_factory=dict)
    readme_excerpt: str = ""

    def render(self) -> str:
        parts = [
            f"**Project type**: {self.project_type}",
            f"**Project name**: {self.project_name or '(unknown)'}",
            "",
            "## Top-level entries",
            "\n".join(f"- {p}" for p in self.top_level) or "_(empty)_",
        ]
        if self.config_files:
            parts.append("")
            parts.append("## Config files")
            for name, excerpt in self.config_files.items():
                parts.append(f"### {name}")
                parts.append("```")
                parts.append(excerpt)
                parts.append("```")
        if self.readme_excerpt:
            parts.append("")
            parts.append("## README excerpt")
            parts.append(self.readme_excerpt)
        return "\n".join(parts)


def scan_workspace(workspace: Path, max_top_level: int = 40) -> WorkspaceSnapshot:
    """Synchronously inspect the workspace.

    Captures: project type marker, top-level entries, config-file excerpts, README head.
    Caps everything to keep the LLM payload small.
    """
    workspace = workspace.resolve()
    snap = WorkspaceSnapshot()

    if not workspace.is_dir():
        return snap

    entries: list[str] = []
    detected_type: str | None = None
    config_excerpts: dict[str, str] = {}

    for entry in sorted(workspace.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        if name in SKIP_DIRS:
            continue
        if entry.is_dir():
            entries.append(f"{name}/")
        else:
            entries.append(name)
            if name in PROJECT_MARKERS and detected_type is None:
                detected_type = PROJECT_MARKERS[name]
                config_excerpts[name] = _read_excerpt(entry, max_chars=2000)
            elif name in PROJECT_MARKERS and name not in config_excerpts:
                config_excerpts[name] = _read_excerpt(entry, max_chars=2000)

    if len(entries) > max_top_level:
        entries = entries[:max_top_level] + [f"... ({len(entries) - max_top_level} more)"]

    snap.project_type = detected_type or "unknown"
    snap.top_level = entries
    snap.config_files = config_excerpts
    snap.project_name = _infer_project_name(workspace, config_excerpts)

    readme = _find_readme(workspace)
    if readme is not None:
        snap.readme_excerpt = _read_excerpt(readme, max_chars=3000)

    return snap


def _infer_project_name(workspace: Path, configs: dict[str, str]) -> str:
    if "pyproject.toml" in configs:
        match = re.search(r'^name\s*=\s*"([^"]+)"', configs["pyproject.toml"], re.MULTILINE)
        if match:
            return match.group(1)
    if "package.json" in configs:
        try:
            data = json.loads(configs["package.json"])
            if isinstance(data, dict) and isinstance(data.get("name"), str):
                return data["name"]
        except json.JSONDecodeError:
            pass
    if "Cargo.toml" in configs:
        match = re.search(r'^name\s*=\s*"([^"]+)"', configs["Cargo.toml"], re.MULTILINE)
        if match:
            return match.group(1)
    return workspace.name


def _find_readme(workspace: Path) -> Path | None:
    for candidate in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
        p = workspace / candidate
        if p.is_file():
            return p
    return None


def _read_excerpt(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text


async def generate_initial(workspace: Path, llm: Any) -> Path:
    """Scan workspace, ask LLM for an initial AGENTS.md, write to workspace/AGENTS.md.

    On any failure (LLM error, malformed JSON), writes a deterministic fallback
    template with default Always Loaded entries and an empty Knowledge Map.
    """
    from jay_llm import Message

    snapshot = scan_workspace(workspace)

    user_prompt = f"""Generate the initial AGENTS.md for this workspace.

{snapshot.render()}
"""

    parsed: dict[str, Any] = {}
    try:
        response = await llm.achat(
            [
                Message(role="system", content=INIT_SYSTEM_PROMPT),
                Message(role="user", content=user_prompt),
            ],
            temperature=0.2,
        )
        parsed = _parse_summary_json(response.content or "")
    except Exception:
        parsed = {}

    always = parsed.get("always_loaded") or []
    if not isinstance(always, list) or not always:
        always = DEFAULT_ALWAYS_LOADED
    always_lines = "\n".join(
        f"- {item}" for item in always if isinstance(item, str) and item.strip()
    ) or "\n".join(f"- {item}" for item in DEFAULT_ALWAYS_LOADED)

    kmap = parsed.get("knowledge_map") or []
    if isinstance(kmap, list) and kmap:
        kmap_lines = "\n".join(
            line.strip() if line.strip().startswith("-") else f"- {line.strip()}"
            for line in kmap
            if isinstance(line, str) and line.strip()
        )
    else:
        kmap_lines = DEFAULT_KNOWLEDGE_MAP

    content = INITIAL_TEMPLATE.format(
        always_loaded=always_lines,
        knowledge_map=kmap_lines,
    )

    target = workspace / "AGENTS.md"
    target.write_text(content, encoding="utf-8")
    return target


async def append_session_summary(
    workspace: Path,
    llm: Any,
    history: list[Any],
    agents_md_path: Path,
) -> tuple[str, str, dict[str, list[str]]]:
    """Propose an updated AGENTS.md based on the session.

    Does NOT write to disk. Returns (new_content, unified_diff, parsed) so the
    caller can show the user a diff and ask for confirmation.

    `history` accepts both jay_llm.Message objects and dict-shaped messages.
    """
    from jay_llm import Message

    if not agents_md_path.is_file():
        raise FileNotFoundError(f"AGENTS.md not found: {agents_md_path}")

    existing = agents_md_path.read_text(encoding="utf-8")
    transcript = _format_history(history)

    user_prompt = f"""Existing AGENTS.md:

```markdown
{existing}
```

Session transcript:

{transcript}
"""

    parsed: dict[str, Any] = {}
    try:
        response = await llm.achat(
            [
                Message(role="system", content=SUMMARY_SYSTEM_PROMPT),
                Message(role="user", content=user_prompt),
            ],
            temperature=0.2,
        )
        parsed = _parse_summary_json(response.content or "")
    except Exception as exc:
        raise RuntimeError(f"LLM summarization failed: {exc!r}") from exc

    new_pitfalls = [
        s.strip()
        for s in (parsed.get("new_pitfalls") or [])
        if isinstance(s, str) and s.strip()
    ]
    new_constraints = [
        s.strip()
        for s in (parsed.get("new_constraints") or [])
        if isinstance(s, str) and s.strip()
    ]

    new_content = existing
    today = datetime.now().strftime("%Y-%m")

    if new_constraints:
        new_content = _merge_into_section(
            new_content,
            "## Always Loaded",
            [f"- {c}" for c in new_constraints],
        )

    if new_pitfalls:
        # Strip the "_(empty ...)_" placeholder if it's the only line in the section
        new_content = _strip_empty_placeholder(new_content, "## Known Pitfalls")
        new_content = _merge_into_section(
            new_content,
            "## Known Pitfalls",
            [f"- {today}: {p}" for p in new_pitfalls],
        )

    diff = "".join(
        difflib.unified_diff(
            existing.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(agents_md_path) + " (current)",
            tofile=str(agents_md_path) + " (proposed)",
            n=2,
        )
    )

    return new_content, diff, {
        "new_pitfalls": new_pitfalls,
        "new_constraints": new_constraints,
    }


def _format_history(history: list[Any], max_chars: int = 20000) -> str:
    if not history:
        return "_(empty)_"
    lines: list[str] = []
    for msg in history:
        role = _msg_attr(msg, "role") or "?"
        content = (_msg_attr(msg, "content") or "").strip()
        if not content or role == "system":
            continue
        lines.append(f"### {role.upper()}\n{content}\n")
    text = "\n".join(lines)
    if len(text) > max_chars:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        text = f"{head}\n\n... (transcript truncated) ...\n\n{tail}"
    return text


def _msg_attr(msg: Any, name: str) -> Any:
    if isinstance(msg, dict):
        return msg.get(name)
    return getattr(msg, name, None)


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _parse_summary_json(text: str) -> dict[str, Any]:
    """Best-effort parse of LLM output. Returns {} on any failure."""
    if not text:
        return {}
    stripped = text.strip()

    fence = _FENCE_RE.match(stripped)
    if fence:
        stripped = fence.group(1).strip()
    else:
        # If there's a code fence somewhere in the text but not at the boundary,
        # try to extract the first fenced block.
        inner = re.search(r"```(?:json)?\s*\n(.*?)\n```", stripped, re.DOTALL)
        if inner:
            stripped = inner.group(1).strip()

    try:
        result = json.loads(stripped)
    except json.JSONDecodeError:
        # Last resort: find the first { ... } object in the text
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return {}
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    return result if isinstance(result, dict) else {}


def _merge_into_section(content: str, section_heading: str, new_lines: list[str]) -> str:
    """Append new_lines to the end of the named section, preserving the file structure.

    The section is identified by a line whose stripped form starts with `section_heading`
    and is either followed by a non-alphanumeric character or ends there. This tolerates
    headings with trailing decoration like `## Known Pitfalls（历史教训）`.

    Appends just before the next `## ` heading, or at end of file if the section is
    the last one.
    """
    if not new_lines:
        return content

    lines = content.splitlines()
    section_start: int | None = None
    section_end: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if section_start is None:
            if _heading_matches(stripped, section_heading):
                section_start = i
            continue
        # Found section start; look for next ## heading
        if stripped.startswith("## ") and not stripped.startswith("### "):
            section_end = i
            break

    if section_start is None:
        # Section not found — append the section at end
        block = ["", section_heading, ""] + new_lines + [""]
        return content.rstrip() + "\n" + "\n".join(block) + "\n"

    if section_end is None:
        section_end = len(lines)

    # Insert before the next section heading, after trimming trailing blank lines
    insert_at = section_end
    while insert_at > section_start + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    new_block = list(lines[:insert_at]) + new_lines + list(lines[insert_at:])
    result = "\n".join(new_block)
    if content.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def _heading_matches(stripped: str, section_heading: str) -> bool:
    """Return True iff ``stripped`` is the section heading we care about.

    Tolerates trailing decoration after a separator (space / colon / parens /
    hyphen / em-dash), so ``## Known Pitfalls (历史教训)`` and
    ``## Known Pitfalls — notes`` both match ``## Known Pitfalls``. Rejects
    anything that immediately continues the heading word (``## Known PitfallsX``).
    """
    if stripped == section_heading:
        return True
    if not stripped.startswith(section_heading):
        return False
    next_char = stripped[len(section_heading):][:1]
    # Whitelist of characters allowed to follow the canonical heading.
    return next_char in {" ", "\t", "(", "（", ":", "：", "-", "—", "/", "|", "·"}


_PLACEHOLDER_RE = re.compile(r"^_\(empty[^)]*\)_$")


def _strip_empty_placeholder(content: str, section_heading: str) -> str:
    """Remove `_(empty — ...)_` placeholder lines inside the named section."""
    lines = content.splitlines()
    in_section = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_section:
            out.append(line)
            if _heading_matches(stripped, section_heading):
                in_section = True
            continue
        if stripped.startswith("## ") and not stripped.startswith("### "):
            in_section = False
            out.append(line)
            continue
        if _PLACEHOLDER_RE.match(stripped):
            continue
        out.append(line)
    result = "\n".join(out)
    if content.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result

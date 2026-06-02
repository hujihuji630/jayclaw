"""Post-write lint orchestration with auto-fix support."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from jay_agent_tools.linters import (
    InternalFieldLinter,
    LintFinding,
    NoPrintLinter,
    PinyinNamingLinter,
    ToolEnvelopeLinter,
)

ALL_LINTERS = [NoPrintLinter(), ToolEnvelopeLinter(), InternalFieldLinter(), PinyinNamingLinter()]


def run_linters(file: Path, source: str) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for linter in ALL_LINTERS:
        findings.extend(linter.check(file, source))
    return findings


def run_ruff(file: Path, fix: bool = True) -> tuple[int, list[dict]]:
    """Run ruff on a file. Returns (num_fixed, remaining_issues).

    If fix=True, ruff auto-fixes what it can in-place first.
    """
    if fix:
        subprocess.run(
            ["ruff", "check", "--fix", "--quiet", str(file)],
            capture_output=True, timeout=30,
        )
    result = subprocess.run(
        ["ruff", "check", "--output-format=json", str(file)],
        capture_output=True, text=True, timeout=30,
    )
    issues = json.loads(result.stdout) if result.stdout.strip() else []
    # Count fixes applied (difference between before-fix and after-fix)
    fixed_count = 0
    if fix and result.returncode == 0:
        fixed_count = 0  # all clean after fix
    return fixed_count, issues


def format_ruff_issues(issues: list[dict]) -> str:
    parts: list[str] = []
    for issue in issues[:10]:  # cap at 10 to avoid flooding context
        loc = issue.get("location", {})
        line = loc.get("row", "?")
        code = issue.get("code", "")
        msg = issue.get("message", "")
        parts.append(f"  {line}:{loc.get('column', '')} [{code}] {msg}")
    if len(issues) > 10:
        parts.append(f"  ... and {len(issues) - 10} more")
    return "\n".join(parts)


def apply_autofixes(source: str, findings: list[LintFinding]) -> tuple[str, list[LintFinding]]:
    lines = source.splitlines(keepends=True)
    applied: list[LintFinding] = []
    for f in sorted(findings, key=lambda x: x.line, reverse=True):
        if not f.autofix:
            continue
        idx = f.line - 1
        if idx < 0 or idx >= len(lines):
            continue
        match = re.search(r"'([^']+)'", f.message)
        if not match:
            continue
        original = match.group(1)
        # If autofix includes quotes, replace the full quoted form
        if f.autofix.startswith('"') and f.autofix.endswith('"'):
            target = f'"{original}"'
            replacement = f.autofix
        else:
            target = original
            replacement = f.autofix
        if target in lines[idx]:
            lines[idx] = lines[idx].replace(target, replacement, 1)
            applied.append(f)
    return "".join(lines), applied


def format_findings(findings: list[LintFinding], applied: list[LintFinding]) -> str:
    parts: list[str] = []
    if applied:
        parts.append(f"✎ {len(applied)} autofix(es) applied:")
        for f in applied:
            parts.append(f"  {f.file}:{f.line} [{f.code}] '{f.autofix}'")
    remaining = [f for f in findings if f not in applied]
    if remaining:
        parts.append(f"⚠ {len(remaining)} issue(s) need manual fix:")
        for f in remaining:
            parts.append(f"  {f.render()}")
    return "\n".join(parts)


def lint_and_fix(file: Path) -> str | None:
    if file.suffix != ".py" or not file.exists():
        return None
    parts: list[str] = []

    # 1. Run ruff (external linter) with auto-fix
    try:
        _, ruff_issues = run_ruff(file, fix=True)
        if ruff_issues:
            parts.append(f"ruff: {len(ruff_issues)} issue(s) remaining after autofix:")
            parts.append(format_ruff_issues(ruff_issues))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # ruff not installed or timed out, skip

    # 2. Run JayClaw custom linters with auto-fix
    source = file.read_text(encoding="utf-8")
    findings = run_linters(file, source)
    if findings:
        new_source, applied = apply_autofixes(source, findings)
        if applied:
            file.write_text(new_source, encoding="utf-8")
        parts.append(format_findings(findings, applied))

    return "\n".join(parts) if parts else None

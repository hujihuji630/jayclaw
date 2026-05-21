"""验证 AGENTS.md 中 Knowledge Map 的每个条目都在 docs/agent-knowledge/ 有对应文档。"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = REPO_ROOT / "AGENTS.md"
KNOWLEDGE_DIR = REPO_ROOT / "docs" / "agent-knowledge"


def _extract_map_entries() -> list[str]:
    """从 AGENTS.md 的 Knowledge Map 段提取条目 ID."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    match = re.search(
        r"## Knowledge Map.*?(?=^## )", text, re.DOTALL | re.MULTILINE
    )
    assert match, "AGENTS.md 缺少 ## Knowledge Map 段"
    section = match.group(0)
    return re.findall(r"^- \*\*([a-z0-9\-]+)\*\*", section, re.MULTILINE)


def test_agents_md_exists():
    assert AGENTS_MD.exists(), "AGENTS.md 不存在"


def test_agents_md_under_100_lines():
    lines = AGENTS_MD.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 100, f"AGENTS.md 超过 100 行（实际 {len(lines)} 行）"


def test_required_sections_present():
    text = AGENTS_MD.read_text(encoding="utf-8")
    for section in ("## Always Loaded", "## Knowledge Map", "## Known Pitfalls"):
        assert section in text, f"AGENTS.md 缺少 {section} 段"


def test_knowledge_map_has_8_entries():
    entries = _extract_map_entries()
    assert len(entries) == 8, f"Knowledge Map 应有 8 条，实际 {len(entries)}: {entries}"


@pytest.mark.parametrize("topic", _extract_map_entries())
def test_each_topic_doc_exists(topic):
    path = KNOWLEDGE_DIR / f"{topic}.md"
    assert path.exists(), f"地图条目 {topic} 缺少对应文档 {path}"


@pytest.mark.parametrize("topic", _extract_map_entries())
def test_each_topic_doc_has_required_sections(topic):
    text = (KNOWLEDGE_DIR / f"{topic}.md").read_text(encoding="utf-8")
    required = (
        "## 它解决什么问题",
        "## 核心机制",
        "## 关键代码锚点",
        "## 常见陷阱",
        "## 修改本机制时的检查清单",
        "## 相关",
    )
    for section in required:
        assert section in text, f"{topic}.md 缺少 {section} 段"

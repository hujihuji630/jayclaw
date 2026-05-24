"""Structured context assembly with prioritized blocks and token budgets.

Inspired by the typed content blocks pattern in attachments.py, this module
structures the system prompt as prioritized, budget-aware blocks with semantic
XML boundary tags. This gives the model clear signal about what each section
IS (identity vs constraints vs project context), and gives the system the
ability to intelligently compress low-priority blocks when over budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .token_counter import count_tokens


@dataclass
class ContextBlock:
    """A typed, prioritized chunk of system prompt content."""

    type: str
    content: str
    priority: int = 3
    max_tokens: int | None = None
    compressible: bool = True
    source: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


class ContextAssembler:
    """Assemble context blocks into a structured system prompt with XML tags.

    Blocks are rendered in priority order (1 = highest). When total token usage
    exceeds the budget, low-priority compressible blocks are truncated first.
    """

    def __init__(self, total_budget: int, model: str | None = None):
        self._blocks: list[ContextBlock] = []
        self._budget = total_budget
        self._model = model

    def add_block(self, block: ContextBlock) -> None:
        self._blocks.append(block)

    def assemble(self) -> str:
        ordered = sorted(self._blocks, key=lambda b: b.priority)
        rendered = self._render_all(ordered)
        total = self._count(rendered)

        if total <= self._budget:
            return rendered

        # Over budget: compress from lowest priority up
        ordered_for_cut = sorted(
            [(i, b) for i, b in enumerate(ordered) if b.compressible],
            key=lambda x: -x[1].priority,
        )

        for idx, block in ordered_for_cut:
            if total <= self._budget:
                break
            block_tokens = self._count(self._render_block(block))
            if block.max_tokens and block_tokens <= block.max_tokens:
                continue
            limit = max(block.max_tokens or 50, 50)
            block.content = self._truncate(block.content, limit)
            new_rendered = self._render_all(ordered)
            total = self._count(new_rendered)

        return self._render_all(ordered)

    def get_utilization(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for block in self._blocks:
            tokens = self._count(self._render_block(block))
            result[block.type] = result.get(block.type, 0) + tokens
        result["_total"] = sum(result.values())
        result["_budget"] = self._budget
        return result

    def _render_all(self, ordered: list[ContextBlock]) -> str:
        parts = [self._render_block(b) for b in ordered if b.content.strip()]
        return "\n\n".join(parts)

    def _render_block(self, block: ContextBlock) -> str:
        tag = block.type
        attr_str = ""
        attrs = dict(block.attrs)
        if block.source:
            attrs["source"] = block.source
        if attrs:
            attr_str = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
        return f"<{tag}{attr_str}>\n{block.content.strip()}\n</{tag}>"

    def _count(self, text: str) -> int:
        return count_tokens(text, model=self._model)

    def _truncate(self, text: str, max_tokens: int) -> str:
        tokens = self._count(text)
        if tokens <= max_tokens:
            return text
        ratio = max_tokens / tokens
        cut = int(len(text) * ratio * 0.9)
        return text[:cut] + "\n[... truncated]"

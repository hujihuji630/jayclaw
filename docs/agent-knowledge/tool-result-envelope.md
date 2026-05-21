# Tool Result Envelope（工具结果包装）

> **何时读本文**：写新工具或修改 ToolResult 序列化时
> **关联源码**：`packages/jay-agent-core/src/jay_agent_core/tools/base.py`

## 它解决什么问题

LLM 看到工具返回值的方式只有"文本"。如果每个工具自己 `return dict` 再交给 Agent 序列化，会出现：成功失败混在一起难以判断、超长结果撑爆 Token、不同工具的错误格式不一致。`ToolResult` 提供唯一的入口与出口契约，让 Agent 主循环可以统一处理 ok/error、按预算截断、并保留可观测元数据。

## 核心机制

1. **统一字段**：`ok: bool`、`data: Any`、`error: str | None`、`meta: dict`。成功路径用 `data`，失败路径用 `error`，永不混用。
2. **serialize(max_chars)**：先尝试一次完整 `json.dumps`；超长时调用结构感知的 `_try_shrink`。
3. **结构感知裁剪 _try_shrink**：
   - **S0**：列表中的 dict 项含已知文本字段（`body/content/text/snippet/...`）时先把它们裁到 200 字，保留 item 数量。
   - **S1**：top-level list 太长，从尾部丢 item。
   - **S2**：dict 嵌套 list 时缩小内嵌 list。
   - **S3**：dict 中的长字符串值按长度倒序按需截断。
4. **fallback 路径**：所有结构感知策略都失败时，wrap 成 `{ok, truncated: true, data_preview: "..."}` 字符串预览，不抛错。
5. **CancelledError**：取消事件触发时由 handler raise，Registry.execute 捕获并返回 `ToolResult(ok=False, error="Cancelled by user")`。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L10-L24 | `ToolResult` 数据类定义 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L26-L71 | `serialize` 主流程 + 兜底 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L74-L77 | `CancelledError` 异常 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L85-L124 | `_compact_items_text` 文本字段裁剪 |
| `packages/jay-agent-core/src/jay_agent_core/tools/base.py` | L127-L210 | `_try_shrink` 四步裁剪策略 |

## 常见陷阱

- **直接 return dict**：handler 不返回 `ToolResult` 会让 Registry.execute 拿到非预期对象；Agent 主循环会报 AttributeError 而不是给 LLM 一个友好错误。
- **error 字段塞 dict**：error 必须是字符串，否则 serialize 兜底 `str(self.error)[:avail]` 会得到 `"{'code':...}"` 一类难看输出。
- **预算估算错误**：`max_chars` 是序列化后的总字符上限，不是 data 字符数；新增字段时记得给 wrapper 留 30 字预算（见 `_try_shrink` 的 `target = budget - 30`）。
- **嵌套递归深度**：`_compact_items_text` 默认 5 层深度限制，深层评论树超过这个深度后不再裁剪——业务有需要时调 `_COMPACT_RECURSION_MAX_DEPTH`。
- **`meta` 字段会被 strip**：序列化时 `meta` 不会写进 LLM 看到的 payload，只用于 Agent 内部转发（如 `requires_confirmation`）。

## 修改本机制时的检查清单

- [ ] 新增字段后跑 `serialize(100)` / `serialize(50)` 确认不会因预算极小而崩
- [ ] 新增已知文本字段时同步更新 `_TEXT_FIELD_NAMES`
- [ ] 任何调整后用 list-of-dict 大对象（>4000 字）测试结构感知路径仍优先于 fallback
- [ ] handler 未捕获的异常应在 Registry 层转为 `ToolResult(ok=False)`，不要让它升到主循环

## 相关
- 关联条目：[tool-lazy-loading](tool-lazy-loading.md)、[ssrf-protection](ssrf-protection.md)

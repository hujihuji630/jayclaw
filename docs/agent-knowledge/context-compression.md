# Context Compression（三级上下文压缩）

> **何时读本文**：改 compress_fn / 上下文压缩策略时
> **关联源码**：`packages/jay-agent-core/src/jay_agent_core/context.py`、`packages/jay-agent-core/src/jay_agent_core/resilience/retry.py`

## 它解决什么问题

随着对话与工具调用累积，messages 列表很快会撑满模型的上下文窗口（gpt-4o 128k、claude-sonnet 200k 都不够多轮 Agent 任务）。本机制按消耗比例阶梯式裁剪：低成本策略先上、保留近期消息、最后一招才花钱让 LLM 总结，避免突然丢上下文导致 Agent "失忆"。

## 核心机制

1. **CompressionConfig** 维护三个阈值（默认 70% / 80% / 90%）和 Level 1 的字符上限（默认 1000）。
2. **Level 1 — 截断 tool 结果**：遍历 messages，把 `role=="tool"` 且 content 超长的截断到 `max_tool_result_chars` 并追加 `[... truncated N chars]` 提示。
3. **Level 2 — 折叠 tool 调用对**：把"assistant tool_calls"与紧随其后的"tool results"成对替换为一条 `[Tool execution: foo, bar - 2 results]` 摘要消息。
4. **Level 3 — LLM 总结中段**：保留 system 消息 + 最后 3 条消息，把中间消息送给 LLM 摘要成 2-3 句，再插回成一条 assistant 消息。失败时 fallback 到 Level 2。
5. **compress_messages 调度器**：根据 `current_tokens / max_tokens` 比例自动选择级别；注意它是同步函数，Level 3 实际由 async `compress_level3` 提供，调用方要自己 await。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-agent-core/src/jay_agent_core/context.py` | L302-L317 | `CompressionConfig` 三阈值定义 |
| `packages/jay-agent-core/src/jay_agent_core/context.py` | L319-L341 | `compress_level1` — 截断 tool 结果 |
| `packages/jay-agent-core/src/jay_agent_core/context.py` | L344-L385 | `compress_level2` — 折叠工具调用对 |
| `packages/jay-agent-core/src/jay_agent_core/context.py` | L388-L450 | `compress_level3` — LLM 摘要 |
| `packages/jay-agent-core/src/jay_agent_core/context.py` | L453-L491 | `compress_messages` 调度器 |
| `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py` | L219-L243 | 压缩在 resilience 中被触发的位置 |

## 常见陷阱

- **Level 2 会丢工具结果细节**：替换为摘要后 LLM 看不到具体返回值，需要工具结果的对话（如"那个搜索给我看一下"）会失败。仅在确实溢出时启用。
- **Level 3 会调一次额外 LLM**：增加延迟和费用，不要在 Level 2 还够用时滥用。配置 `level3_threshold` 时留出余量。
- **first system message 假设**：`compress_level3` 假设 messages[0] 是 system prompt，如果调用方把 system 放在别处，system 内容会被一并摘要导致角色丢失。
- **`compress_messages` 是同步的，Level 3 不会真跑**：注释里写明 "in practice should be called with await compress_level3"，调用方必须自己分支处理 ratio ≥ level3_threshold 的情况。

## 修改本机制时的检查清单

- [ ] 调整阈值时确保 `level1_threshold < level2_threshold < level3_threshold`
- [ ] 改 Level 1 字符上限后跑一次完整对话验证 LLM 仍能基于截断结果继续推理
- [ ] 新增级别时在 `compress_messages` 添加分支并保持同步/异步的清晰分工
- [ ] Level 3 摘要 prompt 必须强调"保留关键决策与上下文"，否则会丢业务信息

## 相关
- 关联条目：[resilience-chain](resilience-chain.md)

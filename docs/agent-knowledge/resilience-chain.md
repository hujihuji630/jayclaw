# Resilience Chain（三层弹性容错）

> **何时读本文**：改 LLM 重试 / Key 轮换 / 三层容错时
> **关联源码**：`packages/jay-agent-core/src/jay_agent_core/resilience/retry.py`、`packages/jay-agent-core/src/jay_agent_core/resilience/profile.py`

## 它解决什么问题

LLM 调用在生产环境会遇到三类故障：**429 速率限制 / API Key 失效**、**上下文超长**、**模型偶发性宕机**。如果只做单次重试，Agent 会因为一次瞬时错误就放弃整轮任务，用户体验极差。本机制把这三类故障拆成三层级联恢复策略，让 Agent 在网络抖动 / Key 用尽 / 上下文爆炸时尽量自愈。

## 核心机制

1. **错误归类**：`_is_error_type` 用关键词集合识别错误属于哪一类（`RATE_LIMIT_ERRORS`、`AUTH_ERRORS`、`TIMEOUT_ERRORS`、`CONTEXT_OVERFLOW_ERRORS`）。
2. **Layer 1 — Profile 轮换**：遇到 rate_limit / auth / timeout 时，`ProfileManager.mark_profile_failed()` 把当前 Key 进入 60 秒冷却，然后 `get_next_profile()` 取下一个可用 Key 继续重试。
3. **Layer 2 — 上下文压缩**：遇到 context_overflow 时调用调用方传入的 `compress_fn(messages)`，把消息列表压短再重试。
4. **Layer 3 — Fallback 模型**：上下文压缩后仍失败，`profile_manager.get_fallback_model(current_model)` 切换到备用模型继续重试。
5. **指数退避**：每轮失败后 `asyncio.sleep(2 ** attempt)`，最多 `max_retries=3` 轮。
6. **可观测性**：每个分支都 `emit()` 一个 `AgentEvent`（`resilience_retry` / `resilience_profile_rotation` / `resilience_compact` / `resilience_fallback`），便于追踪发生了什么。
7. 全部 max_retries 用完后抛 `ResilienceExhaustedError`，附带 `strategies_tried` 列表，调用方可以告诉用户"我试过了 A B C 都不行"。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py` | L19-L46 | `ResilienceExhaustedError` 异常 |
| `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py` | L50-L121 | 错误类型常量与归类函数 |
| `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py` | L124-L296 | `resilient_streaming_call` 流式主循环 |
| `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py` | L299-L464 | `resilient_call` 非流式版本 |

## 常见陷阱

- **生成器内 yield 无法被 try/except**：当前实现把 `async for chunk in llm.astream(...)` 直接放在 try 里，但 Python 协议上 yield 后再抛错只能被外层捕捉。改造时要确认 LLM 适配器在 connection 建立阶段就把错误抛出。
- **profile_manager 状态共享**：跨协程并发调用 resilient_call 时 ProfileManager 的内部状态可能竞态，目前依赖 ProfileManager 自己的锁；自定义实现时必须保证线程安全。
- **errors 关键词列表脆弱**：错误识别是字符串子串匹配，不同 LLM 提供商的报错文本可能差异巨大；新增 provider 时检查 `RATE_LIMIT_ERRORS` 等元组是否覆盖。
- **compress_fn 必须减少消息数**：若返回的消息数 ≥ 原始数则视为无效压缩，会直接进入 Fallback 模型；自定义压缩器要确保真的有缩减。

## 修改本机制时的检查清单

- [ ] 新增错误类型时同时更新对应的关键词元组与 `_should_rotate_profile` 等分发函数
- [ ] 任何新增 `continue` 必须先 `emit` 对应的 `AgentEvent`，否则可观测性会丢失
- [ ] 改 `max_retries` 默认值要评估总耗时上限（指数退避：2+4+8 = 14s）
- [ ] 测试用 mocked LLM 模拟"先 429 后成功"的轮换路径

## 相关
- 关联条目：[context-compression](context-compression.md)

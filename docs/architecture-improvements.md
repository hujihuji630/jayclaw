# JayClaw 架构改进清单

> 基于当前代码的系统性审查，按优先级排列。这些是工程质量问题而非架构方向问题——基础设计决策是正确的。

---

## P0：双注册表统一

**现状**

`agent.py` 同时维护 `self.registry`（同步版，来自 `registry.py`）和 `self.registry_enhanced`（异步版，来自 `tools/registry.py`）。每次注册工具都要写两遍：

```python
self.registry.register(tool)
self.registry_enhanced.register(name=tool.name, handler=make_handler(tool), schema=schema, is_core=True)
```

**问题**

- 双倍维护成本，每加一个工具都要同步两处
- 两个注册表的状态可能不一致（一边注册了另一边没有）
- `run()` 用旧注册表，`arun()` 用新注册表，行为可能不同

**建议**

全面切到 `EnhancedToolRegistry`，删除旧的 `ToolRegistry`。`run()` 方法直接委托给 `arun()` 即可（当前已经是这样做的）。旧注册表的同步执行能力可以通过 `run_in_executor` 在新注册表中实现。

**涉及文件**

- `packages/jay-agent-core/src/jay_agent_core/agent.py`
- `packages/jay-agent-core/src/jay_agent_core/registry.py`（可删除）
- `packages/jay-agent-core/src/jay_agent_core/__init__.py`（移除旧导出）

---

## P1：拆分 `arun()` 主循环

**现状**

`agent.py:arun()` 约 200 行，承担了以下职责：

1. 消息追加到 history
2. Plan nag 注入逻辑
3. LLM 调用（通过 resilient_streaming_call）
4. 工具执行循环
5. `_activate` 信号处理（懒加载工具激活）
6. Steering 消息检查与注入
7. Follow-up 递归处理
8. Billing hook 调用

**问题**

- 单一方法职责过多，难以单独测试某一环节
- 新增功能（如 human-in-the-loop 审批、多 agent 协作）需要侵入这个大方法
- 错误处理粒度粗——一个 try/except 包住整个 LLM 调用

**建议拆分方向**

```
Agent.arun()
  ├── Orchestrator.run_loop()        # 控制循环 + 终止条件判断
  │     ├── _call_llm()              # LLM 调用 + billing
  │     ├── _execute_tools()         # 工具调度 + 并行策略 + activate 信号
  │     └── _check_interrupts()      # steering / follow-up / plan nag
  └── 返回 Response
```

不需要引入新的类——可以先拆成私有方法，保持 `arun()` 作为入口但只做编排。

---

## P2：消除同步/异步桥接重复代码

**现状**

以下模式在项目中出现 5+ 次：

```python
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, self.arun(message))
            return future.result()
    else:
        return loop.run_until_complete(self.arun(message))
except RuntimeError:
    return asyncio.run(self.arun(message))
```

**问题**

- 代码重复，修一处漏另一处
- 在嵌套事件循环场景（Jupyter、某些 Web 框架）下行为不可预测
- `ThreadPoolExecutor` + `asyncio.run` 会创建新的事件循环，可能导致跨线程状态问题

**建议**

封装统一的 `run_sync()` 工具函数：

```python
# jay_agent_core/utils.py
def run_sync(coro):
    """Run an async coroutine synchronously, handling nested event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    
    # Already in a running loop — use thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()
```

所有调用点统一为 `return run_sync(self.arun(message))`。

**涉及文件**

- `packages/jay-agent-core/src/jay_agent_core/agent.py`（`run()`）
- `packages/jay-coding-agent/src/jay_coding_agent/agent.py`（`run_interactive`、`_compact_session`、`_expand_prompt`、`_init_agents_md_now`、`_summarize_to_agents_md_now`）

---

## P3：thinking tags 清理移到 provider 层

**现状**

`agent.py:_clean_content()` 用正则去除 `<think>...</think>` 标签：

```python
content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
content = re.sub(r'</think>', '', content)
```

**问题**

- 假设标签格式固定，嵌套或不完整标签会出错
- Anthropic API 已原生支持 thinking content 与 response content 分离
- 其他 provider（DeepSeek）的 thinking 格式可能不同

**建议**

在 `jay-llm` 的各 provider 实现中，解析 response 时就将 thinking 和 content 分开：

```python
@dataclass
class Response:
    content: str
    thinking: str | None = None  # 新增字段
    model: str = ""
```

Agent 层不再需要做正则清理。

**涉及文件**

- `packages/jay-llm/src/jay_llm/models.py`
- `packages/jay-llm/src/jay_llm/providers/anthropic.py`
- `packages/jay-llm/src/jay_llm/providers/deepseek.py`
- `packages/jay-agent-core/src/jay_agent_core/agent.py`（删除 `_clean_content`）

---

## P4：引入显式 Agent 状态机

**现状**

Agent 状态通过散落的布尔/计数器隐式追踪：

```python
self._plan_used = False
self._rounds_since_plan = 0
```

**问题**

- 状态转换逻辑分散在 `arun()` 各处，难以一眼看出 agent 当前处于什么阶段
- 新增状态（如 "waiting_for_approval"、"delegating"）需要加更多布尔变量
- Observability 无法直接 emit "state_transition" 事件

**建议**

引入轻量状态枚举：

```python
class AgentPhase(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    AWAITING_INPUT = "awaiting_input"
    DELEGATING = "delegating"
    DONE = "done"
```

状态转换集中管理，每次转换 emit 事件。不需要完整的状态机库，一个枚举 + `_transition(new_phase)` 方法即可。

---

## P5：收敛 LLM Provider 支持范围

**现状**

`jay-llm` 支持 15 个 provider（openai、anthropic、google、azure、groq、mistral、openrouter、bedrock、xai、cerebras、cohere、perplexity、deepseek、together、glm）。

**问题**

- 每个 provider 的 streaming 格式、tool calling 格式、error code 都有差异
- 个人维护 15 个 provider 的 API 变更不现实
- 部分 provider（cerebras、cohere、together）用户量极小，投入产出比低

**建议**

分为两个层级：

| 层级 | Provider | 维护承诺 |
|------|----------|----------|
| Tier 1（全功能） | OpenAI、Anthropic、DeepSeek、本地 Ollama | 完整 tool calling + streaming + 测试覆盖 |
| Tier 2（OpenAI 兼容） | 其余所有 | 通过 `base_url` 走 OpenAI 兼容协议，不单独维护 |

Tier 2 的 provider 文件可以保留但标记为 community-maintained，不保证 tool calling 等高级功能。

---

## P6：工具执行结果的结构化返回

**现状**

工具执行结果在 `arun()` 中被序列化为字符串后塞入 history：

```python
tool_content = json.dumps(display_data, ensure_ascii=False)
# 或
tool_content = str(result.data if result.ok else result.error)
```

**问题**

- 丢失了结构化信息（后续压缩时只能按字符数截断，无法按字段重要性裁剪）
- 错误结果和成功结果的格式不统一
- 大型工具结果（如文件内容）序列化后占用大量 token

**建议**

定义标准的工具结果信封（envelope）：

```python
@dataclass
class ToolResultEnvelope:
    tool_name: str
    ok: bool
    summary: str          # 必须 ≤ 200 chars，用于压缩后保留
    data: Any = None      # 完整数据，压缩时可丢弃
    error: str | None = None
```

压缩时 Level 1 保留 `summary + data[:N]`，Level 2 只保留 `summary`。

---

## 执行建议

| 优先级 | 改进项 | 预估工作量 | 风险 |
|--------|--------|-----------|------|
| P0 | 双注册表统一 | 2-3 天 | 中（需要全面回归测试） |
| P1 | 拆分 arun() | 1-2 天 | 低（纯重构，行为不变） |
| P2 | 同步桥接统一 | 半天 | 低 |
| P3 | thinking 移到 provider | 1 天 | 低 |
| P4 | Agent 状态机 | 1 天 | 低 |
| P5 | Provider 收敛 | 半天（标记+文档） | 无 |
| P6 | 工具结果信封 | 1-2 天 | 中（影响压缩逻辑） |

建议按 P0 → P2 → P1 → P3 的顺序执行。P2 最简单且收益立竿见影，P0 是最大的技术债。

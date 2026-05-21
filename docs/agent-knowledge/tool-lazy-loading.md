# Tool Lazy Loading（工具懒加载）

> **何时读本文**：改 discover_tools / _activate / 工具按需暴露逻辑时
> **关联源码**：`packages/jay-agent-core/src/jay_agent_core/tools/registry.py`、`packages/jay-agent-core/src/jay_agent_core/tools/handlers_core.py`、`packages/jay-agent-core/src/jay_agent_core/tools/schemas.py`

## 它解决什么问题

当工具数量超过 20 个时，把全部 schema 一次性塞给 LLM 会浪费 token、拖慢首 Token、并诱导 LLM 误选不相关工具（例如简单聊天却调用 `post_x`）。本机制让 LLM 启动时只看到 4 个 **核心工具**（think/plan/discover_tools/get_current_time），其余工具按关键词按需"解锁"。

## 核心机制

1. `CORE_TOOL_NAMES`（schemas.py）定义永远可见的工具集合，schema 通过 `get_core_schemas()` 暴露给 LLM。
2. `DEFERRED_TOOL_INDEX` 维护"关键词 → 工具名列表"映射（如 `"web" → ["search_web", "read_webpage"]`）。
3. LLM 调用 `discover_tools(query="web")` 后，handler 在 `registry_enhanced._schemas` 中按关键词模糊匹配，把命中的工具名放入 `data._activate` 字段返回。
4. Agent 主循环看到 `_activate` 字段后，调用 `ToolRegistry.activate_tools(names)`，把工具加入 `_discovered` 集合；下一轮 `get_schemas()` 就会把它们一起暴露给 LLM。
5. 序列化前 `strip_internal_fields()` 剥离所有 `_` 开头的键（包括 `_permission`、`_activate`），防止内部元数据污染 LLM 视野。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-agent-core/src/jay_agent_core/tools/schemas.py` | L54-L61 | `CORE_TOOL_NAMES` 定义 |
| `packages/jay-agent-core/src/jay_agent_core/tools/schemas.py` | L171-L180 | `DEFERRED_TOOL_INDEX` 关键词索引 |
| `packages/jay-agent-core/src/jay_agent_core/tools/schemas.py` | L214-L233 | `strip_internal_fields` + `get_core_schemas` |
| `packages/jay-agent-core/src/jay_agent_core/tools/handlers_core.py` | L101-L165 | `handle_discover_tools` 关键词匹配 |
| `packages/jay-agent-core/src/jay_agent_core/tools/registry.py` | L201-L235 | `get_schemas` + `activate_tools` 闭环 |

## 常见陷阱

- 漏剥离 `_activate` 字段：工具开发者在 schema 顶层加内部字段时没加 `_` 前缀，结果 LLM 在后续请求里看到这个字段并尝试模仿调用，产生大量无意义的 `"_activate": ...` 参数。
- `_discovered` 集合不持久化：跨会话恢复时 LLM 必须重新调用 `discover_tools`，没意识到这点的实现会让 Agent 在第二轮对话里突然找不到上轮"用过"的工具。
- 关键词匹配只看名字不看描述：如果工具描述里有重要类别词（"reddit social"），但名字没有，简单的 `query in name` 匹配会漏掉它——当前实现已同时匹配 `name` 和 `desc`。

## 修改本机制时的检查清单

- [ ] 修改后用 `strip_internal_fields` 测试任何新增的内部字段都被剥离
- [ ] `CORE_TOOL_NAMES` 仍然 ≤ 5 个，避免开局就把上下文撑爆
- [ ] `_activate` 返回值是工具名字符串列表（不是 schema 对象）
- [ ] 新增关键词时同时更新 `DEFERRED_TOOL_INDEX` 和对应工具的 schema 描述

## 相关
- 关联条目：[tool-result-envelope](tool-result-envelope.md)、[pinyin-naming](pinyin-naming.md)

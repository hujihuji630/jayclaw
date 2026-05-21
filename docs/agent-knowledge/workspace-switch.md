# Workspace Switch（运行时切换工作目录）

> **何时读本文**：改 change_workspace / 会话跨目录恢复时
> **关联源码**：`packages/jay-coding-agent/src/jay_coding_agent/agent.py`、`packages/jay-coding-agent/src/jay_coding_agent/tools.py`

## 它解决什么问题

CodingAgent 的文件 / shell 工具会绑定一个根目录（`workspace`）来防止跨目录写入。早期实现要切换 workspace 必须重启整个 Agent 进程——对话历史、工具状态、技能缓存全部丢失。本机制让 Agent 在运行中通过 `change_workspace(new_path)` 原地切换，保留 LLM 上下文和会话。

## 核心机制

1. **Path 校验**：`Path(new_workspace).resolve()` 把入参解析为绝对路径，`exists()` + `is_dir()` 双重校验，避免传入文件路径或不存在的目录。
2. **重新实例化文件类工具**：`FileTools(str(self.workspace))`、`CodeTools()`、`ShellTools()` 用新 workspace 重建，旧实例丢弃。
3. **遍历替换工具**：对每个新 tool 实例用 `dir()` 反射出 `Tool` 类型属性，组装成新的 `new_tools` 列表。
4. **registry_enhanced 重注册**：`registry.register(name, handler, schema, ...)` 用 `make_handler(t)` 闭包包装新工具的 `aexecute`，覆盖旧条目。`ToolRegistry.register` 内部用 `_lock` 保证并发安全。
5. **保留 LLM / session / skills**：CodingAgent 的 `llm`、`session`、`skill_manager`、`extension_manager` 字段均保持不变，对话历史与已加载技能不受影响。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-coding-agent/src/jay_coding_agent/agent.py` | L324-L375 | `change_workspace` 完整流程 |
| `packages/jay-coding-agent/src/jay_coding_agent/agent.py` | L344-L356 | 用反射组装新工具列表 |
| `packages/jay-coding-agent/src/jay_coding_agent/agent.py` | L358-L375 | `make_handler` 闭包 + 重注册 |
| `packages/jay-agent-core/src/jay_agent_core/tools/registry.py` | L45-L86 | `ToolRegistry.register` 加锁覆盖 |

## 常见陷阱

- **没切的不是工具，是 LLM 看到的 cwd 上下文**：LLM 之前对话里看到的 "我在 /a/b/c" 没自动更新；需要在切换后给 LLM 一条系统消息提示。
- **Skill 的工作目录假设**：某些 skill 缓存了 workspace 路径，重建工具但不重置 skill 会导致 skill 误读旧目录文件。
- **闭包陷阱**：`make_handler(t)` 必须是真闭包（每次调用形成新的 `t` 绑定），不能写成 `for t: handler = lambda ...: t.aexecute(...)`，否则所有 handler 都引用最后一个 t。
- **未关闭的 ShellTools 子进程**：旧 ShellTools 可能持有打开的子进程；切换时应显式 close，否则资源泄漏。

## 修改本机制时的检查清单

- [ ] 切换后用 list_files 跑一次确认看到的是新目录
- [ ] 切换前若有正在执行的工具调用，必须等它完成或取消
- [ ] 新加入的有状态工具（如 BrowserTool）记得加入 change_workspace 的重建列表
- [ ] LLM 提示中"当前工作目录"信息更新到新 workspace

## 相关
- 关联条目：[tool-lazy-loading](tool-lazy-loading.md)

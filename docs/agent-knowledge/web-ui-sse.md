# Web UI SSE（流式状态推送与中止）

> **何时读本文**：改 web-ui SSE 流 / 中止按钮 / 状态流时
> **关联源码**：`packages/jay-web-ui/src/jay_web_ui/server.py`

## 它解决什么问题

Web UI 用 Server-Sent Events 把 Agent 的实时状态推给浏览器（token 流、工具调用开始/结束、思考事件）。对长任务用户必须能"中止"——早期实现只在前端断开 EventSource，但后端协程仍在跑，用户以为停了，结果还在烧 token、还在写文件。本机制让前后端协同：前端按按钮 → 通过 `/cancel` HTTP 端点把 cancel event 设为 set → 后端 Agent 主循环每轮检查 cancel.is_set() 并立刻退出。

## 核心机制

1. **SSE 流**：FastAPI `EventSourceResponse`（或手写 chunked response）按 `data: {json}\n\n` 格式推送，事件类型分 `token` / `tool_start` / `tool_result` / `done` / `error`。
2. **会话级 cancel event**：每次开启对话创建一个 `asyncio.Event()`，存到 `sessions[session_id].cancel`。
3. **/cancel 端点**：POST `/api/cancel/{session_id}` → 服务端 `event.set()`。
4. **Agent 协作中止**：主循环每轮 `if cancel and cancel.is_set(): break`；工具执行内部 `Registry._execute_tool` 也定期检查。
5. **前端清理**：cancel 调用成功后前端关闭 EventSource、清除 token 累积、显示"已中止"提示。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-web-ui/src/jay_web_ui/server.py` | TBD | SSE 流 endpoint（搜 `EventSource` 或 `text/event-stream`） |
| `packages/jay-web-ui/src/jay_web_ui/server.py` | TBD | `/cancel` 端点 |
| `packages/jay-agent-core/src/jay_agent_core/tools/registry.py` | L304-L360 | `Registry.execute` cancel.is_set() 检查 |
| `packages/jay-agent-core/src/jay_agent_core/tools/registry.py` | L398-L420 | `_execute_tool` 重试循环中检查 cancel |

> 注：本条目仅作为地图引用，按 P0 边界不修改 web-ui 源码；具体行号待 P1+ 实测后回填。

## 常见陷阱

- **前端 close EventSource 不通知后端**：浏览器关闭 EventSource 是优雅关闭，但 Python asyncio 不会立刻感知；必须显式 `/cancel`。
- **取消事件粒度太粗**：只在工具间检查导致"已经在跑的工具"无法立即停。需要把 cancel 事件传到 `httpx.AsyncClient.aclose()` / subprocess.kill 等点。
- **session 共享一个 cancel 导致连环误伤**：用户连开两个对话时，cancel 事件不能跨 session 共享，否则 cancel A 会断 B。
- **SSE proxy 缓冲**：Nginx / CloudFlare 默认会缓冲响应，需 `X-Accel-Buffering: no` 头才能让事件即时到达浏览器。
- **断线重连**：EventSource 浏览器会自动重连，重连后没带 cancel 状态可能让 Agent 重新发流；要么禁用自动重连，要么 server 端识别同一 session 不允许重启。

## 修改本机制时的检查清单

- [ ] 取消测试：长 prompt 启动后 1 秒内点中止，server 端应在 ≤2 秒内停止 LLM token 流并写入 done 事件
- [ ] 取消事件传到工具内部的子进程（特别是 ShellTools）
- [ ] /cancel 端点鉴权：避免他人 session_id 被外部猜测后强行中断
- [ ] 前后端 done/error 事件格式约定文档化

## 相关
- 关联条目：[resilience-chain](resilience-chain.md)

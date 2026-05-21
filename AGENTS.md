# AGENTS.md

> 这是一份**地图**，不是百科全书。Agent 启动只读本文，按需用 read_knowledge 拉取详情。
> 总行数控制在 100 行以内；条目过期请及时移除。

## Always Loaded（硬约束，永远遵守）

- 不要 commit `.env`、API key、`*.pem`、`*.key`、`credentials.json`
- 工具返回值必须用 `ToolResult` 包装，不要直接 return dict（详见 tool-result-envelope）
- 工具 schema 内部字段必须以 `_` 开头（会被自动剥离，详见 tool-lazy-loading）
- 任何 LLM 调用必须经过 `resilient_streaming_call` 包裹（详见 resilience-chain）
- 修改 `packages/<pkg>/` 前必须先读对应 `packages/<pkg>/README.md`
- 新建工具时函数和变量必须用英文命名（详见 pinyin-naming）
- 写网络相关工具必须调用 `validate_url`（详见 ssrf-protection）

## Knowledge Map（按需加载，调用 read_knowledge）

> read_knowledge 工具将在 P1-1 实现；当前阶段地图条目作为"目录"供人类与 Agent 参考。

### Agent 内核
- **tool-lazy-loading** — 改 discover_tools / _activate / 工具按需暴露逻辑时
- **resilience-chain** — 改 LLM 重试 / Key 轮换 / 三层容错时
- **context-compression** — 改 compress_fn / 上下文压缩策略时
- **workspace-switch** — 改 change_workspace / 会话跨目录恢复时

### 工具系统
- **tool-result-envelope** — 写新工具或修改 ToolResult 序列化时
- **ssrf-protection** — 写网络工具或修改 validate_url 时
- **pinyin-naming** — 新工具命名、重构变量名时

### 集成层
- **web-ui-sse** — 改 web-ui SSE 流 / 中止按钮 / 状态流时

## Known Pitfalls（历史教训，每条 1 行）

> 每次踩坑后追加一行。格式：`日期: 简述 → 详情链接`

- 2025-04: pig→jay 重命名时漏改 export.py / share.py / agent.py 内嵌字符串 → 改进点详解.md
- 2025-03: web-ui 中止按钮只切前端没切后端协程 → 改进点详解.md 改动六
- 2025-03: 工具懒加载漏剥离 `_activate` 字段，污染 LLM 视野 → 改进点详解.md 改动三
- 2025-03: 搜索功能只接付费 API，无 key 时无 fallback 直接报错 → 改进点详解.md 改动四
- 2025-03: 切换工作目录需重启整个 Agent，对话历史丢失 → 改进点详解.md 改动五

## How to Use This Map

- Agent 启动时本文件自动注入；调用 `read_knowledge("<topic>")` 拉取地图条目对应文档
- 条目 ≥ 30 时切换为混合检索（P1-1 演进路径）
- 维护：任务失败 → 写入 Known Pitfalls；新增非平凡设计 → 写入 Knowledge Map

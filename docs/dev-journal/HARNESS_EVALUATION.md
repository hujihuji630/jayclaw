# JayClaw Harness 工程评估报告

> 评估日期：2026-05-21
> 评估对象：`jayclaw-main` 项目（基于 pig-mono 改造的多包 Python Agent 框架）
> 评估坐标系：Level 0（无 Harness）→ Level 4（自治循环）

---

## 一、TL;DR（先看结论）

| 维度 | 当前等级 | 关键证据 |
|---|---|---|
| **整体评级** | **Level 2 中段（偏向 Level 3，但缺自治循环）** | 有完备的反馈回路与可插拔架构，但缺少多 Agent 分工、持久化记忆与无人值守循环 |
| Level 0 → 1 | ✅ 完全达成 | AGENTS.md、ruff、pre-commit、mypy 全部就位 |
| Level 1 → 2 | ✅ 基本达成 | 三平台 CI/CD 矩阵、Codecov、pytest 覆盖率 89.46%、可观测性事件、计费钩子 |
| Level 2 → 3 | ⚠️ 半成品 | 工具懒加载/扩展插件/技能系统具备"分层上下文"形态，但**没有真正的多 Agent 分工和跨会话持久化记忆** |
| Level 3 → 4 | ❌ 未达成 | 无后台并行、无自动清理、无自修复机制，弹性容错只能算"自重试"而非"自修复" |

**最该改进的三件事（按 ROI 排序）：**

1. **引入子 Agent 编排框架**（解锁 Level 3，工作量中等，收益最大）
2. **把 memory.py 从 InMemoryProvider 升级为持久化语义记忆**（Level 3 的标配，目前完全缺失跨会话记忆）
3. **建一个"自治循环 + 自修复"骨架**（迈入 Level 4 的入场券，可以从 CI 自动修复失败的测试开始）

---

## 二、按 Level 逐项打分

### Level 0：无 Harness ✅ 已远超

JayClaw 显然不是"随手写 prompt"的草台班子，结构化程度很高，跳过。

---

### Level 1：基础约束 ✅ 完全达成

| 特征 | 项目实现 | 证据位置 |
|---|---|---|
| AGENTS.md | ✅ 有 | [examples/context/AGENTS.md](examples/context/AGENTS.md) + 运行时 `SystemPromptBuilder` 自动注入 |
| 基础 Linter | ✅ 有 | ruff（`.pre-commit-config.yaml` + CI 中 `ruff check / ruff format --check`） |
| 类型检查 | ✅ 有（弱） | mypy 在 CI 里跑，但 `|| true` 兜底——失败不阻断（半成品） |
| 手动测试 | ✅ 有 | `scripts/test.sh`、pytest.ini、tests/ 目录 |
| 安全约束 | ✅ 加分项 | [tools/base.py:217-309](packages/jay-agent-core/src/jay_agent_core/tools/base.py#L217-L309) 内置 SSRF 防护、私网 IP 屏蔽、元数据端点黑名单 |
| 工具结果包络 | ✅ 加分项 | `ToolResult` 标准化 ok/data/error + 结构化截断（`_try_shrink`），防止单条工具输出炸上下文 |

**结论：Level 1 不仅达成，还做了超出 Level 1 标准的"输出截断 + URL 安全校验"等防御性工程。**

---

### Level 2：反馈回路 ✅ 基本达成

| 特征 | 项目实现 | 证据 |
|---|---|---|
| CI/CD 集成 | ✅ | [.github/workflows/ci.yml](.github/workflows/ci.yml) 跑 3 OS × 3 Python = 9 矩阵作业 |
| 自动化测试 | ✅ | 40+ 测试文件，覆盖率 **89.46%**（coverage.xml `line-rate="0.8946"`） |
| 进度追踪 | ✅ | `AgentEventCallback` + `AgentEvent` 把 agent_start / turn / tool / resilience 全部事件化 |
| 计费/成本 | ✅ | `BillingHook` 协议 + `/cost` 命令实时统计 token & 费用 |
| 持续构建 | ✅ | CI 里 build + twine check 验证每个包能正常打包 |
| 文档检查 | ✅ | CI 强制每个 package 必须有 README.md |
| Codecov 上报 | ✅ | ubuntu-3.11 作业上传覆盖率到 Codecov |

**Level 2 标准下唯一的小瑕疵：**

- ❌ **CI 不阻断 mypy 失败**（`mypy packages/ || true`）——典型的"假装做了类型检查"。
- ❌ **没有 Agent 行为回归测试**（只测代码单元，没测 Agent 在固定 prompt 下的输出回归）。
- ❌ **没有性能/延迟基准**——没法发现 token 用量或响应延迟的退化。

---

### Level 3：专业化 Agent ⚠️ 半成品（约 40% 达成）

这一档是 JayClaw 的**主要短板**，逐条对照：

#### 3.1 多 Agent 分工 ❌ **基本没有**

- 全局搜索 `subagent | sub_agent | spawn_agent | orchestrat` 在 packages/ 下**只有 messenger 的消息路由编排器**（不是 Agent 编排）。
- 单个 `Agent` 类（[agent.py:23](packages/jay-agent-core/src/jay_agent_core/agent.py#L23)）是**唯一**的执行单元，没有"规划 Agent / 执行 Agent / 评审 Agent"等角色拆分。
- 没有任何 Agent-to-Agent 的消息总线或任务分发机制。

#### 3.2 分层上下文 ⚠️ 形式上有，实质偏弱

- 形式：`SystemPromptBuilder` + `AGENTS.md` + `SYSTEM.md` + `SKILL.md` 已有分层注入。
- 短板：分层是**静态**的——启动时拼好就固定，**没有按当前子任务动态切上下文**的能力。

#### 3.3 持久化记忆 ❌ **几乎没有**

- 当前实现：[memory.py](packages/jay-agent-core/src/jay_agent_core/memory.py) 只有 `InMemoryProvider`（进程内列表），加一个 `MemoryProvider` Protocol 占位。
- 会话级别有持久化（`.sessions/coding-session.jsonl`、`save_state` / `from_state`），但这是**会话存档**，不是 Level 3 期望的"跨会话长期记忆"——
  - 没有事实抽取（"用户偏好 X"、"项目用 Y 测试框架"）
  - 没有向量检索/语义检索
  - 没有 `MEMORY.md` 这类索引文件
  - 没有遗忘/更新策略

#### 3.4 工程师定位 ⚠️ 部分达成

- 扩展插件系统（`ExtensionAPI`、`@api.tool`、`@api.command`、`@api.on`）算"设计环境"的能力。
- 技能系统（`.agents/skills/SKILL.md`）也算给 Agent 设定专项能力的入口。
- 但是没有**给 Agent 设定"质量门"**（例如"必须跑测试才能交付"、"必须 lint 才能 commit"）的固化机制。

#### 3.5 已经具备的"Level 3 雏形" ✅

| 能力 | 评价 |
|---|---|
| 工具懒加载（`discover_tools` + `_activate`） | **Level 3 思路**，按需暴露工具，避免一次性灌满 |
| 内部字段约定（`_` 前缀剥离） | 工程化非常好，避免内部信号污染 LLM 视野 |
| 三层弹性容错（Key 轮换 / 压缩 / 模型降级） | 已经接近"自修复"的入口（详见 4.2） |
| 扩展插件 + 技能 | 给 Level 3 留好了接口，差实际的子 Agent 接入 |

---

### Level 4：自治循环 ❌ 未达成（约 15% 雏形）

| 特征 | 实现状况 |
|---|---|
| 无人值守并行化 | ❌ 没有任务队列/调度器，Agent 是请求-响应模型 |
| 自动清理 | ❌ 没有 .sessions 自动归档/淘汰，没有 worktree/沙箱清理 |
| 自修复 | ⚠️ 弹性容错算"自重试"——只能修复**外部错误**（网络/Key/上下文），无法修复**自身错误**（生成的代码跑不通） |
| 后台执行 | ❌ 没有 `run_in_background`、没有 cron、没有定时任务 |
| 沙箱隔离 | ❌ 工具执行没有沙箱（SSRF 是网络层防护，不是进程级沙箱） |

唯一可以算 Level 4 雏形的是**弹性容错链 + 事件回调**——如果把"测试失败"也接入这个链路，理论上可以触发自动重试/重写。

---

## 三、Harness 标准下的差距矩阵

```
┌─────────────────────────────────────────────────────────────────────┐
│ Level 0  ████████████████████████████████████████████████████ 100%  │
│ Level 1  ████████████████████████████████████████████████████ 100%  │
│ Level 2  ████████████████████████████████████████████ 85%           │
│ Level 3  ████████████████ 40%                                        │
│ Level 4  ██████ 15%                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

**项目当前重心定位：稳固的 Level 2，跨入 Level 3 的工程基础已经搭好，差关键骨架。**

---

## 四、改进方案（按行业标准 P0/P1/P2 对照）

> 本节直接对齐业界 harness 实践三档清单（Hashimoto / OpenAI / Anthropic / Dex Horthy / Carlini）。
> 每条行动都给出：**业界做法 → JayClaw 现状 → 缺口 → 落地路径**。

---

### P0：可以马上做（1~3 天，性价比最高）

#### P0-1：创建**地图式** AGENTS.md（只放目录，按需加载）

| 维度 | 内容 |
|---|---|
| **业界实践** | Hashimoto——每一行 AGENTS.md 对应一个历史失败案例，犯错后立即追加；OpenAI——AGENTS.md ≤ 100 行，只做**目录**不塞内容，子文档按需引用 |
| **核心理念** | **AGENTS.md = 地图，不是百科全书**。Agent 启动只读地图，按当前任务关键词决定钻进哪个具体路径。这样 (1) Smart Zone 不被无关知识污染；(2) 知识库可以无限扩张而不撑爆上下文 |
| **JayClaw 现状** | ⚠️ 只有 [examples/context/AGENTS.md](examples/context/AGENTS.md) 一份"模板示例"，76 行，**内容是全量写死的**——code style、project structure、testing 全堆在一个文件里；根目录还缺一份；不是地图、是说明书 |
| **缺口** | (1) 位置错；(2) **结构错**——应该是目录而非平铺内容 |
| **落地路径** | **第 1 步：定义地图结构**。在仓库根新建 `AGENTS.md`，全文 ≤ 100 行，**只**包含以下三段：<br><br>　• `## Always Loaded`（≤ 20 行）— 必须默认加载的硬约束（例：禁止 commit `.env`、工具结果必须用 `ToolResult` 包装、内部字段加 `_` 前缀）<br>　• `## Knowledge Map`（地图主体，每条 1 行）— 格式：<br>　　```<br>　　- [tool-lazy-loading](docs/agent-knowledge/tool-lazy-loading.md) — 何时读：要修改 discover_tools 或 _activate 逻辑时<br>　　- [resilience-chain](docs/agent-knowledge/resilience-chain.md) — 何时读：要改 LLM 重试 / Key 轮换 / 上下文压缩时<br>　　- [workspace-switch](docs/agent-knowledge/workspace-switch.md) — 何时读：要改 change_workspace 或会话恢复时<br>　　- [pinyin-naming](docs/agent-knowledge/pinyin-naming.md) — 何时读：写新工具或重命名时<br>　　```<br>　• `## Known Pitfalls`（≤ 30 行）— 历史失败案例索引（每条 1 行 + 详情链接，**这是 Hashimoto 标准**）<br><br>**第 2 步：把现有知识拆进 `docs/agent-knowledge/`**——从 [改进点详解.md](改进点详解.md) 反向提炼，每个非平凡设计一个 md 文件，每文件 ≤ 200 行<br><br>**第 3 步：写 `read_knowledge(topic)` 工具**——这是地图能"按需加载"的关键。Agent 看到地图条目里的关键词后调用该工具拉对应文档进上下文。具体实现见 P1-1<br><br>**第 4 步：钩子化维护**——在 `arun()` 失败路径加 hook：任务失败时提示"是否要把这条记入 `## Known Pitfalls`"，避免地图随时间过期 |

**地图式 AGENTS.md 示例骨架**（直接可用）：

```markdown
# AGENTS.md

> 这是一份**地图**，不是百科全书。Agent 启动只读本文，按需用 read_knowledge 拉取详情。

## Always Loaded（硬约束，永远遵守）
- 不要 commit `.env`、`api_key`、`*.pem`
- 工具返回值必须用 `ToolResult` 包装，不要直接 return dict
- 工具 schema 内部字段必须以 `_` 开头（会自动剥离，不会发给 LLM）
- 修改 packages/ 前必须先读对应 package 的 README.md
- 任何 LLM 调用必须经过 resilient_streaming_call 包裹

## Knowledge Map（按需加载，调用 read_knowledge）

### Agent 内核
- **tool-lazy-loading** — 改 discover_tools / _activate / 工具按需暴露逻辑时
- **resilience-chain** — 改 LLM 重试 / Key 轮换 / 三层容错时
- **context-compression** — 改 compress_fn / 上下文压缩策略时
- **workspace-switch** — 改 change_workspace / 会话跨目录恢复时

### 工具系统
- **tool-result-envelope** — 写新工具或修改 ToolResult 序列化时
- **ssrf-protection** — 写网络工具或修改 validate_url 时
- **pinyin-naming** — 新工具命名、重构变量名时（含拼音词典）

### 集成层
- **web-ui-sse** — 改 web-ui SSE 流 / 中止按钮 / 状态流时
- **messenger-adapters** — 改 Slack/Discord/飞书适配时
- **billing-cost** — 改 token 统计 / /cost 命令 / BillingHook 时

## Known Pitfalls（历史教训，每条 1 行）

- 2025-04: pig→jay 重命名时漏改 export.py / share.py 内嵌字符串 → 参见 commit XXX
- 2025-03: web-ui 中止按钮只切前端没切后端协程 → 改进点详解.md 改动六
- 2025-03: 工具懒加载漏剥离 _activate 字段，污染 LLM 视野 → 改进点详解.md 改动三
- ...（每次踩坑追加一行）

## How to Use This Map

调用 `read_knowledge("<topic>")` 拉取具体文档。地图条目数 ≥ 30 时，先 grep 地图找最相关 3 条再读。
```

#### P0-2：构建自定义 Linter + **自带修复指令**

| 维度 | 内容 |
|---|---|
| **业界实践** | OpenAI——Linter 报错不只是"你错了"，而是"你错了，应该这样改：……"；Agent 看到错误就有可执行的下一步 |
| **JayClaw 现状** | ✅ ruff 已经接入，✅ 有 `check_pinyin_naming` 这种**面向 Agent 的领域 Linter**（建议 `chaxun` → `query` 并给出 camelCase/snake_case 两种风格）——这是非常贴近本条标准的工程<br>❌ 但其他规则（ruff 默认输出、SSRF 拦截、URL 校验失败）的报错都是**纯描述性**，没有"建议修改方案" |
| **缺口** | 把 `check_pinyin_naming` 的"诊断 + 修复建议"模式推广到其他自定义检查 |
| **落地路径** | 1. 新增 `packages/jay-agent-tools/src/jay_agent_tools/linters/` 模块，统一 LintFinding 数据结构：`{file, line, code, message, suggestion, autofix?}`<br>2. 第一批接入：<br>　• `check_no_print` — 检测残留 `print()`，建议改成 `logger.debug()`<br>　• `check_tool_result_envelope` — 检测工具直接 return dict 没用 `ToolResult` 包装<br>　• `check_internal_field_prefix` — 检测 tool schema 里没加 `_` 前缀的内部字段<br>　• `check_pinyin_naming`（已有，迁过来）<br>3. 在 `URLValidationError` / `ToolResult.error` 里加上"如何修复"段落（例：blocked URL 报错时附"是否需要 allow_private=True"）<br>4. 把 `mypy packages/ || true` 的 `|| true` 去掉——核心包先严格，外围逐步收紧 |

#### P0-3：把团队知识放进仓库（仓库即事实来源）

| 维度 | 内容 |
|---|---|
| **业界实践** | OpenAI——Slack / Wiki / Docs 里的知识对 Agent 不稳定可见，必须沉淀到仓库里 |
| **JayClaw 现状** | ⚠️ [改进点详解.md](改进点详解.md) 和 [面试准备.md](面试准备.md) 是非常好的"内部知识"，但 (1) 不在 `.agents/` 路径下，Agent 不会自动加载；(2) 没有索引；(3) 工具懒加载、`_activate` 信号、三层弹性这些**非平凡设计**只在 README 散落 |
| **缺口** | 知识有，但 Agent 拿不到 |
| **落地路径** | 1. 新建 `docs/agent-knowledge/` 目录，把分散在 README/改进点详解里的"非平凡设计"抽出来：<br>　• `tool-lazy-loading.md` — `discover_tools` 协议<br>　• `internal-field-convention.md` — `_` 前缀剥离<br>　• `resilience-chain.md` — 三层容错的触发条件矩阵<br>　• `workspace-switch.md` — `change_workspace` 不重启的语义<br>2. 在根 `AGENTS.md` 加索引：`## Knowledge Base` 段列出每个文档+一行说明<br>3. 在 `SystemPromptBuilder` 加路径白名单：启动时把 `docs/agent-knowledge/*.md` 的摘要拼进 system prompt 后段 |

---

### P1：P0 稳了之后再补（1~3 周，进入 Level 3）

#### P1-1：实现地图按需加载机制（`read_knowledge` 工具 + 懒注入）

| 维度 | 内容 |
|---|---|
| **业界实践** | OpenAI——根 AGENTS.md ~100 行只做**目录**，按需引用 `docs/X.md`，避免单文件膨胀（与 P0-1 的地图理念是一对：P0-1 画地图，P1-1 让地图能被点开） |
| **JayClaw 现状** | ✅ P0-1 完成后地图已经画好；✅ `SystemPromptBuilder` + `SKILL.md` 的**分层架子**已有；❌ 但目前所有上下文是**全量静态拼接**——启动时把能找到的都塞进去 |
| **缺口** | 地图画完了，但没有"按需打开"的机制 |
| **落地路径** | **第 1 步：实现 `read_knowledge` 工具**<br>　文件位置：`packages/jay-agent-core/src/jay_agent_core/tools/handlers_core.py`<br>　```python<br>　@tool(description="按主题读取 docs/agent-knowledge/ 下的知识文档")<br>　def read_knowledge(topic: str) -> ToolResult:<br>　    path = Path("docs/agent-knowledge") / f"{topic}.md"<br>　    if not path.exists():<br>　        return ToolResult(ok=False, error=f"Unknown topic: {topic}. 可用: ...")<br>　    return ToolResult(ok=True, data=path.read_text())<br>　```<br>　**关键点**：在 `Always Loaded` 工具集里默认暴露这一个工具，让 Agent 可以从地图直接钻入子文档<br><br>**第 2 步：改造 `SystemPromptBuilder` 支持懒注入**<br>　给 `SystemPromptBuilder` 加 `lazy_sections: dict[trigger_keyword, doc_path]` 参数<br>　• 默认只注入 `AGENTS.md` 全文（≤ 100 行）<br>　• 当 Agent 调用 `read_knowledge(topic)` 时，把对应文档**一次性**注入并标记，避免重复加载<br>　• 已加载文档列表记录在 session metadata 里，可被 `/context` 命令查看<br><br>**第 3 步：地图条目自动校验**<br>　CI 加一条 `tests/test_knowledge_map.py`：解析 `AGENTS.md` 的 `Knowledge Map` 段，确保每条引用的 `docs/agent-knowledge/*.md` 真实存在——避免地图过期指向死链<br><br>**第 4 步：上下文预算可视化**<br>　`/context` 命令显示：<br>　```<br>　地图基础: 1.2K tokens (AGENTS.md)<br>　已加载: tool-lazy-loading (3.4K), resilience-chain (2.1K)<br>　总占用: 6.7K / 128K (5.2%)<br>　```<br><br>**第 5 步：写测试验证机制**<br>　• `test_default_context_under_budget` — 默认上下文 ≤ X tokens<br>　• `test_lazy_load_appends_correctly` — read_knowledge 后正确合并<br>　• `test_lazy_load_dedup` — 同一主题不重复加载 |

**地图机制的副作用**：实现完 P0-1 + P1-1 后，JayClaw 的上下文管理就有了完整闭环——

```
启动加载: AGENTS.md (地图, ~100 行)
    ↓
Agent 看任务关键词
    ↓
调 read_knowledge("X")
    ↓
对应文档注入上下文（一次性）
    ↓
继续工作
    ↓
任务完成 → 不主动卸载（同 session 内复用）
新 session → 重新只加载地图
```

**演进路径：地图条目 > 30 时启用混合检索**

地图初期（< 30 条）用纯**字符串匹配**就够（Agent 看条目里的"何时读"关键词决定）；条目膨胀后会出现"找不到最相关文档"的问题。届时升级为**业界标准的混合检索**：

| 检索方式 | 强项 | 弱项 |
|---|---|---|
| **关键词检索**（BM25 / FTS5） | 精确命中专有名词（"discover_tools"、"_activate"） | 不懂同义词（"重试机制" vs "resilience-chain"） |
| **向量检索**（embedding 余弦） | 懂语义相似（"Key 轮换" 也能命中 "resilience-chain"） | 对低频专有名词召回差 |
| **混合检索**（RRF / weighted fusion） | 两者优势互补 | 实现成本高一些 |

**实施路径（在 P1-1 完成 3 个月后**或**地图条目 > 30 时**触发）：

1. 用 sqlite + FTS5 建关键词索引（**零依赖**，sqlite 是 Python 标准库）
2. 用 `sentence-transformers` 的轻量模型（如 `all-MiniLM-L6-v2`，22MB）建 embedding 索引，本地存 numpy 数组
3. `read_knowledge` 接受两种调用形态：
   - `read_knowledge(topic="tool-lazy-loading")` — 精确按主题（地图直接命中）
   - `read_knowledge(query="如何避免给 LLM 看到内部字段")` — 自然语言查询，走混合检索
4. 用 **Reciprocal Rank Fusion（RRF）** 融合两路结果：`score = Σ 1/(k + rank_i)`，k=60 是经验常数
5. 返回 top-3 文档片段而非全文，进一步省 token

**为什么不一开始就上混合检索**：(1) 增加 sentence-transformers 依赖（数百 MB 模型）；(2) 30 条以内字符串匹配召回率够用；(3) 过早优化会让 P0-1 的"地图"机制失去"轻"的优势。**等地图真正长起来再升级**。

#### P1-2：**建立进度文件和功能列表**（结构化 JSON）

| 维度 | 内容 |
|---|---|
| **业界实践** | Anthropic——初始化 Agent + 编码 Agent 两阶段；用 JSON 追踪每个功能的状态（待开发/进行中/已完成/已验证），Agent 不容易乱改结构化数据 |
| **JayClaw 现状** | ⚠️ `.sessions/coding-session.jsonl` 是**会话日志**，不是"任务/功能进度"；`max_rounds_with_plan` + plan tool 算是个微型雏形，但没有持久化的"功能清单" |
| **缺口** | 没有一份"项目状态台账"让 Agent 跨会话知道"还有什么没做" |
| **落地路径** | 1. 新增 `.agents/progress.json`：`{"features": [{"id", "name", "status", "owner", "files", "tests", "notes"}], "updated_at"}`<br>2. 新增工具 `update_progress(feature_id, status, notes)`——只能改字段值，不能改 schema<br>3. `Planner` Agent（P1-4）的产出直接落进这个 JSON，`Reviewer` 验收后改 status<br>4. CI 加一条检查：`progress.json` schema 合法、status 必须是合法枚举值 |

#### P1-3：给 Agent **端到端验证能力**（像用户一样验证）

| 维度 | 内容 |
|---|---|
| **业界实践** | Anthropic——用 Playwright / Puppeteer MCP 让 Agent 真打开浏览器点按钮验证 |
| **JayClaw 现状** | ❌ Web UI（[web_example.png](packages/jay-web-ui/web_example.png)）改动只能人眼看；CLI 改动也只有单元测试，没有"启动 → 输入 → 验证输出"的端到端工具 |
| **缺口** | Agent 改完代码无法自验证"功能是不是真的好了" |
| **落地路径** | 1. 在 `jay-agent-tools` 下新增 `e2e/` 子包：<br>　• `browser_check(url, action_script)` — 用 Playwright 启动 chromium，跑预设脚本，截图<br>　• `cli_check(command, expect_pattern)` — subprocess 跑 CLI，断言输出<br>　• `http_check(url, expected_status, expected_body_contains)` — 验证 web-ui SSE 流是否正常<br>2. 让这三个工具走"高风险确认门"（项目已有 confirmation gate 机制）<br>3. 第一个落地用例：`tests/e2e/test_web_ui_smoke.py` —— 启动 start_web_ui.py、打开 8000、发一条消息、断言收到 SSE chunk |

#### P1-4：**控制上下文利用率 ≤ 40%**（Smart Zone / Dumb Zone）

| 维度 | 内容 |
|---|---|
| **业界实践** | Dex Horthy——Smart Zone（前 40% 上下文）放高信噪比信息，Dumb Zone（后 60%）容忍噪声；超过 40% 用增量执行/分块降低污染 |
| **JayClaw 现状** | ✅ 三层弹性的"上下文压缩"已经在了，✅ `ToolResult._try_shrink` 做了结构化截断（**这就是控制污染的关键工程**）；❌ 但没有**实时利用率指标**，也没有 Smart/Dumb Zone 概念——压缩是被动触发，不是主动管理 |
| **缺口** | 从"撑爆才压缩"升级到"主动监控 + 主动分段 + 用户决策" |
| **落地路径** | **第 1 步：实时指标**<br>　在 `AgentEventCallback` 里新增 `context_utilization` 指标，每轮算 `current_tokens / model_max_tokens`<br><br>**第 2 步：三档触发动作**<br><br>　**≥ 40% 触发"决策点"**（核心改进）—— 不是简单的"黄色提醒"，而是**让用户参与上下文管理决策**。Web UI / CLI 都弹出三选一：<br>　```<br>　⚠️ 上下文已用 42% (54K / 128K)<br>　Smart Zone 即将告罄，建议：<br>　 [1] 继续在当前窗口（接受可能的污染）<br>　 [2] 生成任务交接文档 → 新开会话（推荐）<br>　 [3] 主动压缩当前历史（保留要点丢弃细节）<br>　```<br><br>　**≥ 70% 触发自动压缩**（不再询问，直接调 `compress_fn`）<br><br>　**≥ 85% 强制交接**（已经迟了，没得选）：自动生成 handoff.md，提示"请新开窗口继续"<br><br>**第 3 步：实现"任务交接 md"工具**（关键新工具）<br>　`generate_handoff_doc(reason: str) -> Path`<br>　产出 `.sessions/handoff_<timestamp>.md`，结构如下：<br>　```markdown<br>　# 任务交接文档<br>　## 原任务<br>　{从 history 第一条 user message 抽取}<br>　## 已完成步骤<br>　{扫描 tool_call 历史，列出已成功调用的工具 + 关键产出}<br>　## 当前状态<br>　{文件改动列表（git status）+ 最后一次 tool_result 摘要}<br>　## 待办事项<br>　{从最后一条 assistant message 抽取 TODO}<br>　## 重要决策<br>　{扫描历史中的"我决定 / 我选择"等关键节点}<br>　## 推荐下一步<br>　{LLM 生成的一句话建议}<br>　```<br>　新会话启动时检测 `.sessions/handoff_*.md`，自动注入到 system prompt<br><br>**第 4 步：UI/CLI 集成**<br>　• Web UI：在标题栏加进度条显示利用率，40%/70%/85% 三档变色<br>　• CLI：新增 `/context` 命令显示当前占用<br>　• 都接 `/handoff` 命令，用户可以**主动**触发交接（不等到 40% 才能用）<br><br>**第 5 步：测试**<br>　• 构造长对话验证 40%/70%/85% 三档都触发对应事件<br>　• 验证 handoff.md 产出后新会话能正确恢复上下文 |

**为什么"用户决策"比"自动压缩"更重要**：
压缩 = 信息有损，用户最清楚"哪些细节是这次任务关键，哪些可以丢"。Smart Zone 用满到 40% 才弹窗，给用户主导权——这是 Dex Horthy 的 Smart Zone 理念落到 UX 层的具体形态。

---

### P2：有余力再考虑（4~8 周，迈向 Level 4）

#### P2-1：**Agent 专业化分工**（去重 / 优化 / 文档 Agent）

| 维度 | 内容 |
|---|---|
| **业界实践** | Carlini——按职责拆 Agent：去重 Agent（清理冗余）、优化 Agent（提性能）、文档 Agent（写注释）。每个携带更少无关信息，留在 Smart Zone |
| **JayClaw 现状** | ❌ 单 Agent 架构，所有职责挤在一个上下文里——读代码、改代码、写测试、跑测试全在 `arun()` 一个循环里轮转 |
| **缺口** | 缺**多 Agent 编排框架**（原 P1-1 评估，现归到 P2 是因为它依赖 P1-1~P1-4 的上下文管理打好基础） |
| **落地路径** | 1. 新增 `packages/jay-agent-core/src/jay_agent_core/orchestration/` 模块：<br>　• `AgentRole` 协议<br>　• `Orchestrator` 类（按 DAG 调度多个 `Agent` 实例）<br>　• 复用现有 `arun()` 当每个角色的核心，不重写<br>2. 第一版先做"Planner → Executor"两段式，跑通流水线<br>3. 第二版加 Reviewer 角色 + 三个质量门工具（`run_pytest` / `run_ruff` / `run_mypy`）<br>4. 第三版按 Carlini 拆出 `DocAgent`（专门维护 docstring）、`RefactorAgent`（专门去重）<br>5. 利用现有 `span_id` / `parent_span_id` 追踪跨 Agent 调用栈<br>6. 工具懒加载（`discover_tools`）天然契合：Planner 看全集、Executor 只看激活集 |

#### P2-2：**定期垃圾回收**（清理速度 ≥ 生成速度）

| 维度 | 内容 |
|---|---|
| **业界实践** | OpenAI——后台清理 Agent 定期跑：归档旧 session、删冗余 worktree、压缩日志 |
| **JayClaw 现状** | ❌ `.sessions/` 只增不减；❌ 没有 worktree 隔离机制；❌ 没有定时任务调度器 |
| **缺口** | 全套缺失 |
| **落地路径** | 1. 引入 APScheduler 或自写轻量 cron<br>2. 内置回收策略：<br>　• `.sessions/*.jsonl` — 30 天前归档到 `.sessions/archive/`，1 年后删除<br>　• 临时 worktree — 任务结束 + 无未提交改动 → 自动删除<br>　• 失败工具调用日志 — 保留 7 天<br>　• `htmlcov/` / `__pycache__/` — CI 跑 `git clean -fdx` 自检<br>3. 暴露 `gc_status` 工具让 Agent 自己能查"清理速度 vs 生成速度"<br>4. 报警阈值：清理积压 > 100MB 或 > 7 天没清理时主动告警 |

#### P2-3：**可观测性集成**（性能从感觉变成可测量）

| 维度 | 内容 |
|---|---|
| **业界实践** | OpenAI——接入 Chrome DevTools / Profiler 让 Agent 用真实指标决策，而不是猜"是不是太慢了" |
| **JayClaw 现状** | ✅ `AgentEventCallback` + `AgentEvent` 事件链已经存在；✅ `BillingHook` 跟踪 token；❌ 但只输出到 `/cost` 命令，**没有持久化指标**、没有时序数据库、没有 dashboard、没有"延迟回归"告警 |
| **缺口** | 事件流是"管道"，缺"水库" |
| **落地路径** | 1. 加 `MetricsHook` 协议，第一版用 SQLite 存：<br>　• `llm_call_latency_ms`（按 provider/model 分维度）<br>　• `tool_call_latency_ms`（按工具名分维度）<br>　• `context_utilization`（衔接 P1-4）<br>　• `resilience_layer_triggered`（哪一层被触发了多少次）<br>2. 可选：导出 Prometheus exporter，或直接接 OpenTelemetry（注意 P0 阶段不建议做，这里是 P2）<br>3. 跑一个 `metrics_snapshot` 工具，让 Agent 在性能优化任务里可以**先量再改**<br>4. CI 加性能基准回归：核心场景延迟 / token 用量超过 baseline 20% 报警（不阻断） |

---

### 业界标准对照速查表

| 行业实践 | 业界代表 | JayClaw 现状 | 优先级 |
|---|---|---|---|
| AGENTS.md 持续维护（地图式） | Hashimoto + OpenAI | ⚠️ 位置错 + 结构错（百科式） | P0-1 |
| Linter 自带修复指令 | OpenAI | ✅ 部分（拼音工具）+ ❌ 未推广 | P0-2 |
| 仓库即事实来源 | OpenAI | ⚠️ 知识在 README/markdown 散落 | P0-3 |
| 地图按需加载（`read_knowledge`） | OpenAI | ❌ 没有懒注入机制 | P1-1 |
| 结构化进度文件 | Anthropic | ❌ 没有 | P1-2 |
| 端到端验证能力 | Anthropic | ❌ 没有 | P1-3 |
| 上下文利用率 ≤ 40%（含用户决策） | Dex Horthy | ⚠️ 被动压缩、无监控、无交接 | P1-4 |
| 混合检索（BM25 + 向量） | RAG 业界共识 | ❌ 没有（地图 < 30 条不急做） | P1-1 演进 |
| Agent 专业化分工 | Carlini | ❌ 单 Agent | P2-1 |
| 后台垃圾回收 | OpenAI | ❌ 没有 | P2-2 |
| 可测量的可观测性 | OpenAI | ⚠️ 有事件、无指标库 | P2-3 |

---

## 五、不建议立即做的事（避免过度工程）

| 想做的事 | 为什么先别做 | 什么时候做 |
|---|---|---|
| 引入向量数据库做记忆 | 当前规模用文件+grep 就够，向量库会带来运维成本 | 知识文档 > 50 篇时再考虑 |
| 接入 LangGraph / AutoGen 等大框架 | JayClaw 自身架构清晰、已有扩展点，硬接外部框架会撕裂代码风格 | 除非要接入外部 Agent 生态 |
| 把所有 LLM 调用都加 OpenTelemetry | 事件系统已经存在，先把事件用起来再考虑接外部 APM | P2-3 的 MetricsHook 跑稳后 |
| 给每个工具加单独沙箱 | 先用路径白名单 + worktree 隔离，进程级沙箱是 Level 4 后期 | P2-1 多 Agent 跑通后 |
| 一步到位做三段式编排 | 先跑通 Planner→Executor 两段式，验证 DAG 调度可行 | 两段式稳定 2 周后 |

---

## 六、改进路线图（建议时序）

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Day 1-3   [P0-1] 根目录 AGENTS.md（含 Known Pitfalls）                  │
│  Day 4-7   [P0-2] Linter 自带修复指令 + 去掉 mypy 的 || true             │
│  Day 8-10  [P0-3] docs/agent-knowledge/ + SystemPromptBuilder 接入       │
│  Week 2    [P1-1] AGENTS.md 拆成目录 + 懒加载子文档                      │
│  Week 3    [P1-2] .agents/progress.json + update_progress 工具           │
│  Week 4    [P1-3] Playwright/CLI/HTTP 三个端到端验证工具                 │
│  Week 5    [P1-4] context_utilization 指标 + 40/70/85 三档触发           │
│  Week 6-7  [P2-1] Planner/Executor 两段式编排（含质量门）                │
│  Week 8+   [P2-2/P2-3] 垃圾回收 + Metrics 持久化（按需启动）             │
└──────────────────────────────────────────────────────────────────────────┘
```

每一阶段结束都建议在 README 顶部加一条"当前 Harness 等级：Level X"，把工程能力外化成可感知的标签。

---

## 七、写给项目主理人的话

JayClaw 现在的代码质量、CI 覆盖、容错设计在**单 Agent 框架**里已经处于上游水平——SSRF 防护、结构化截断、`_activate` 信号、`/cost`、三层弹性，这些细节都是"做过事的人才会想到"的工程。

但要从 **"一个好 Agent 框架"** 跨到 **"一套真正意义上的 Harness"**，差的不是更多功能，而是**让 Agent 不再是单点**：
- 多角色协作让 Agent 学会分工
- 持久化记忆让 Agent 跨会话学习
- 自治循环让 Agent 在没人盯着时也能干活

把 P0 当作收尾、P1 当作下一阶段的主线，6 周内可以把项目稳稳推到 **Level 3 中段**，再用 4~8 周自然进入 **Level 4 雏形**。

---

*评估文件：`HARNESS_EVALUATION.md`*
*评估者：Claude Opus 4.7（基于代码静态勘察）*

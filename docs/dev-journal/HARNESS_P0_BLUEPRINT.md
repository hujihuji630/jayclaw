# JayClaw Harness P0 实施设计图

> **本文档的读者**：执行改进任务的 AI 助手（非人类）
> **配套文档**：[HARNESS_EVALUATION.md](HARNESS_EVALUATION.md)（评估报告，提供 WHY）
> **本文档作用**：提供精确到文件路径、函数签名、验收命令的 **HOW**
> **范围闸门**：**只做 P0 三项任务**。任何超出 P0 的改动都不要做，包括但不限于 P1-1（read_knowledge 工具的真实实现）、P1-4（context_utilization 指标）等

---

## 0. 执行前必读（强制约定）

### 0.1 工作目录与平台

- 仓库根目录：`c:\pycharm project\jayclaw-main-1.1\`（Windows + bash shell）
- 路径使用：写文档/代码时用 **相对路径**（如 `docs/agent-knowledge/`）；运行命令时用 **bash 风格**（如 `c:/pycharm project/jayclaw-main/`，禁用反斜杠）
- 编辑器换行：与现有文件保持一致（CRLF）

### 0.2 不要碰的文件（硬约束）

| 路径 | 原因 |
|---|---|
| `packages/jay-llm/**` | LLM 适配层，本次任务无关 |
| `packages/jay-messenger/**` | 消息适配器，本次任务无关 |
| `packages/jay-web-ui/**` | UI 层，P0 不涉及 |
| `packages/jay-tui/**` | UI 层，P0 不涉及 |
| `examples/**`（除 `examples/context/AGENTS.md` 外，**只读不改**） | 示例代码 |
| `.sessions/`、`.idea/`、`.vscode/`、`htmlcov/`、`coverage.xml` | 运行时/IDE 产物 |
| `LICENSE`、`uv.lock`、`pyproject.toml`（根级别） | 元数据 |
| 任何 `__pycache__/` | 编译缓存 |
| `面试准备.md`、`改进点详解.md` | 私人文档，可读不可改 |

### 0.3 允许新建文件的路径

| 路径 | 用途 |
|---|---|
| `AGENTS.md`（仓库根） | P0-1 主产出 |
| `docs/agent-knowledge/*.md` | P0-3 主产出 |
| `packages/jay-agent-tools/src/jay_agent_tools/linters/**` | P0-2 主产出 |
| `packages/jay-agent-tools/tests/test_linters_*.py` | P0-2 测试 |
| `tests/test_knowledge_map.py` | P0-1 自洽测试 |
| `.github/workflows/ci.yml` | 仅允许修改 mypy 行（见 P0-2 步骤 4） |

### 0.4 提交规范

- 每个 P0 任务一个 commit，commit message 格式：`[P0-N] <简短描述>`
- **不要 git push**
- **不要 git rebase / reset --hard**
- 不要修改 `.gitignore`（除非有具体添加项需要）
- 不要创建分支（在当前 `main` 上直接提交即可，由人类决定后续）

### 0.5 通用验收命令

每个任务都用以下命令最终验证：

```bash
# 语法 & 格式
ruff check packages/ AGENTS.md 2>/dev/null || ruff check packages/
ruff format --check packages/

# 类型检查（核心包必须通过，外围允许失败）
mypy packages/jay-agent-core/src packages/jay-llm/src

# 测试
pytest packages/jay-agent-tools/tests/test_linters_*.py -v   # P0-2
pytest tests/test_knowledge_map.py -v                         # P0-1
```

### 0.6 当遇到歧义时

按以下顺序判断：

1. 看本文档对应任务的"验收标准"段
2. 看 `HARNESS_EVALUATION.md` 对应任务的"业界实践"段
3. **不要发挥**——按最小可行实现做完，停下来等下一轮指令，不要做"顺便也加上"的事

---

## 1. 任务依赖图

```
P0-1 (AGENTS.md 地图)
  └── 依赖：无
  └── 产出：AGENTS.md（仅占位条目，docs/agent-knowledge/ 真实文件由 P0-3 创建）

P0-3 (docs/agent-knowledge/ 知识库)
  └── 依赖：P0-1（要看 AGENTS.md 的 Knowledge Map 条目列表）
  └── 产出：6 个 .md 文档

P0-2 (Linter 自带修复指令)
  └── 依赖：无（可与 P0-1/P0-3 并行）
  └── 产出：linters/ 模块 + 4 个检查器 + 测试

最终验证：
  └── 依赖：P0-1 + P0-2 + P0-3 全部完成
  └── 产出：tests/test_knowledge_map.py 验证地图条目与实际文件一致
```

**强烈推荐执行顺序：P0-1 → P0-3 → P0-2 → 最终验证**

理由：P0-1 定义 Knowledge Map 条目（约束 P0-3 的产出范围）；P0-3 落实文档（让 P0-1 不指空链接）；P0-2 完全独立（可放后或并行）。

---

## 2. 任务 P0-1：地图式 AGENTS.md

### 2.1 目标

在仓库根创建 `AGENTS.md`，全文 **≤ 100 行**，结构如 `HARNESS_EVALUATION.md` §四 P0-1 中"地图式 AGENTS.md 示例骨架"所示。

### 2.2 输入

- 阅读：[HARNESS_EVALUATION.md](HARNESS_EVALUATION.md) 第 162-202 行（骨架模板）
- 阅读：[改进点详解.md](改进点详解.md) 全文（提取 Known Pitfalls 的素材）
- 阅读：[README.md](README.md) 第 238-330 行（提取"非平凡设计"作为 Knowledge Map 条目）

### 2.3 产出

唯一新建文件：`AGENTS.md`（仓库根，绝对路径 `c:/pycharm project/jayclaw-main/AGENTS.md`）

### 2.4 具体步骤

**步骤 1：确定 Knowledge Map 条目（先列条目再写文档）**

从以下来源提取，**共 8 条**（不要多不要少，让 P0-3 可控）：

| 条目 ID（文件名 stem） | 触发关键词 | 内容来源（参考） |
|---|---|---|
| `tool-lazy-loading` | discover_tools / _activate / 工具按需暴露 | 改进点详解.md 改动二、三 |
| `resilience-chain` | LLM 重试 / Key 轮换 / 三层容错 | README.md 三层弹性容错段 |
| `context-compression` | compress_fn / 上下文压缩 / 三级压缩 | README.md + retry.py 注释 |
| `workspace-switch` | change_workspace / 跨目录切换 | 改进点详解.md 改动五 |
| `tool-result-envelope` | ToolResult / _try_shrink / 工具结果包装 | packages/jay-agent-core/src/jay_agent_core/tools/base.py:11-72 |
| `ssrf-protection` | validate_url / 私网拦截 / 元数据端点 | packages/jay-agent-core/src/jay_agent_core/tools/base.py:217-309 |
| `pinyin-naming` | check_pinyin_naming / 拼音变量 / 命名 | 改进点详解.md 改动四 4.3 |
| `web-ui-sse` | SSE 流 / 中止按钮 / web-ui 状态流 | 改进点详解.md 改动六 |

**步骤 2：写入 AGENTS.md**

严格遵循下方模板填空（**不要新增段落、不要改变段落顺序**）。占位符 `{...}` 全部替换为实际内容。

```markdown
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
```

### 2.5 验收标准

执行以下检查，**所有都必须通过**：

```bash
# 1. 文件存在且非空
test -s "c:/pycharm project/jayclaw-main/AGENTS.md" && echo "OK: 文件存在"

# 2. 行数 ≤ 100（含空行）
wc -l "c:/pycharm project/jayclaw-main/AGENTS.md"
# 期望输出第一个数字 ≤ 100

# 3. 包含三个必备段落
grep -c "^## Always Loaded" "c:/pycharm project/jayclaw-main/AGENTS.md"   # 期望 1
grep -c "^## Knowledge Map" "c:/pycharm project/jayclaw-main/AGENTS.md"   # 期望 1
grep -c "^## Known Pitfalls" "c:/pycharm project/jayclaw-main/AGENTS.md"  # 期望 1

# 4. Knowledge Map 条目数 = 8
grep -c "^- \*\*" "c:/pycharm project/jayclaw-main/AGENTS.md"  # 期望 8
```

### 2.6 边界（不要做）

- 不要修改 `examples/context/AGENTS.md`（保留它作为"示例"）
- 不要尝试实现 `read_knowledge` 工具（这是 P1-1）
- 不要把 `改进点详解.md` 内容拷进 AGENTS.md——只引用文件名
- 不要超过 100 行（如果超了，砍 Known Pitfalls 而非 Knowledge Map）

---

## 3. 任务 P0-3：知识库 docs/agent-knowledge/

### 3.1 目标

为 P0-1 列出的 **8 个 Knowledge Map 条目**各创建一份 markdown 文档，让地图不指向死链。

### 3.2 输入

- 必读：`AGENTS.md`（P0-1 产出）
- 8 个条目的内容来源已在 §2.4 步骤 1 表中给出
- 关键源码（必读对应文件后再写文档）：
  - `tool-lazy-loading` → `packages/jay-agent-core/src/jay_agent_core/tools/registry.py`
  - `resilience-chain` → `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py`
  - `context-compression` → `packages/jay-agent-core/src/jay_agent_core/resilience/retry.py:219-243`
  - `workspace-switch` → `packages/jay-coding-agent/src/jay_coding_agent/agent.py`（搜索 `change_workspace`）
  - `tool-result-envelope` → `packages/jay-agent-core/src/jay_agent_core/tools/base.py:1-210`
  - `ssrf-protection` → `packages/jay-agent-core/src/jay_agent_core/tools/base.py:217-309`
  - `pinyin-naming` → `packages/jay-agent-tools/src/jay_agent_tools/`（搜 `check_pinyin_naming`）
  - `web-ui-sse` → `packages/jay-web-ui/src/jay_web_ui/server.py`

### 3.3 产出

8 个新建文件：

```
docs/agent-knowledge/tool-lazy-loading.md
docs/agent-knowledge/resilience-chain.md
docs/agent-knowledge/context-compression.md
docs/agent-knowledge/workspace-switch.md
docs/agent-knowledge/tool-result-envelope.md
docs/agent-knowledge/ssrf-protection.md
docs/agent-knowledge/pinyin-naming.md
docs/agent-knowledge/web-ui-sse.md
```

### 3.4 统一模板（每个文档严格使用）

每个文件 **≥ 30 行、≤ 200 行**，使用以下模板：

```markdown
# {Topic Title}

> **何时读本文**：{从 AGENTS.md 的 Knowledge Map 触发关键词复制}
> **关联源码**：{相对路径，可多条}

## 它解决什么问题

{2-4 句话说明这个机制要解决的具体痛点，引用 1 个具体场景}

## 核心机制

{用 5-10 句话说明工作原理。可以用编号列表。}

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/.../foo.py` | L42-L68 | {做什么} |
| ... | ... | ... |

## 常见陷阱

- {从 改进点详解.md 或 README.md 提炼的"容易踩坑的点"}
- {同上，至少 2 条}

## 修改本机制时的检查清单

- [ ] {改完后必须验证的事项 1}
- [ ] {事项 2}
- [ ] {事项 3}

## 相关
- 关联条目：[xxx](xxx.md)（如有）
```

### 3.5 验收标准

```bash
# 1. 8 个文件全部存在
for topic in tool-lazy-loading resilience-chain context-compression workspace-switch tool-result-envelope ssrf-protection pinyin-naming web-ui-sse; do
  test -s "c:/pycharm project/jayclaw-main/docs/agent-knowledge/${topic}.md" \
    && echo "OK: ${topic}" \
    || echo "MISSING: ${topic}"
done

# 2. 每个文件行数 30 ≤ N ≤ 200
find "c:/pycharm project/jayclaw-main/docs/agent-knowledge" -name "*.md" -exec wc -l {} \;

# 3. 每个文件包含 6 个必备小节
for f in "c:/pycharm project/jayclaw-main/docs/agent-knowledge"/*.md; do
  for section in "## 它解决什么问题" "## 核心机制" "## 关键代码锚点" "## 常见陷阱" "## 修改本机制时的检查清单" "## 相关"; do
    grep -q "$section" "$f" || echo "MISSING section '$section' in $f"
  done
done
```

### 3.6 边界

- **不要重写源码**——只是描述现有代码
- **不要复制大段代码进文档**——用"行号锚点 + 简述"即可
- **代码锚点必须真实存在**——写完后用 `Read` 工具校验对应行号确实指向相关代码
- 如果某个条目对应的源码 < 50 行，文档也对应缩短（但仍 ≥ 30 行）

---

## 4. 任务 P0-2：Linter 自带修复指令

### 4.1 目标

新增 `packages/jay-agent-tools/src/jay_agent_tools/linters/` 模块，落地 **4 个自定义 Linter**，每个错误都带"建议修复方案"。同时去掉 CI 中 mypy 的 `|| true`。

### 4.2 输入

必读：
- `packages/jay-agent-tools/src/jay_agent_tools/` 现有结构（确认在哪个子包加 linters/）
- `.github/workflows/ci.yml:67-69`（mypy 行）
- `packages/jay-agent-core/src/jay_agent_core/tools/base.py:11-24`（`ToolResult` 数据结构，linter 复用其字段命名风格）

### 4.3 产出

```
packages/jay-agent-tools/src/jay_agent_tools/linters/__init__.py
packages/jay-agent-tools/src/jay_agent_tools/linters/base.py             # LintFinding + 基础接口
packages/jay-agent-tools/src/jay_agent_tools/linters/no_print.py         # 检查器 1
packages/jay-agent-tools/src/jay_agent_tools/linters/tool_envelope.py    # 检查器 2
packages/jay-agent-tools/src/jay_agent_tools/linters/internal_field.py   # 检查器 3
packages/jay-agent-tools/src/jay_agent_tools/linters/pinyin_naming.py    # 检查器 4（迁移占位）
packages/jay-agent-tools/tests/test_linters_base.py
packages/jay-agent-tools/tests/test_linters_no_print.py
packages/jay-agent-tools/tests/test_linters_tool_envelope.py
packages/jay-agent-tools/tests/test_linters_internal_field.py
```

修改：
```
.github/workflows/ci.yml  # 仅改 mypy 行
```

### 4.4 base.py 必须实现的接口

```python
# packages/jay-agent-tools/src/jay_agent_tools/linters/base.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LintFinding:
    """A single lint finding. Every field is mandatory except autofix.

    The `suggestion` field is what makes this Agent-friendly: it must tell
    the reader HOW to fix, not just what is wrong.
    """
    file: Path
    line: int
    code: str           # 短码，如 "JC001"
    message: str        # 描述：发生了什么
    suggestion: str     # 建议：怎么改（必填，禁止为空字符串）
    autofix: str | None = None  # 可选：可直接替换的字符串

    def render(self) -> str:
        """Render as a single-line human-readable string."""
        s = f"{self.file}:{self.line} [{self.code}] {self.message}\n  → {self.suggestion}"
        if self.autofix:
            s += f"\n  ✎ autofix: {self.autofix}"
        return s


class Linter(Protocol):
    """All linters must implement this Protocol."""
    code: str  # e.g. "JC001"
    name: str

    def check(self, file: Path, source: str) -> list[LintFinding]:
        ...
```

### 4.5 四个检查器的规则

| 检查器 | 代码 | 规则 | 建议示例 |
|---|---|---|---|
| `no_print` | JC001 | 检测 `print(` 调用（排除 tests/ 目录和 `# noqa: JC001` 注释行） | "改用 logger.debug() 或 logger.info()" |
| `tool_envelope` | JC002 | 检测 `@tool` 装饰函数的 return 语句返回非 `ToolResult` 类型（启发式：`return {` / `return [` / `return "` 直接返回字面量） | "用 ToolResult(ok=True, data=...) 包装返回值" |
| `internal_field` | JC003 | 检测 tool schema 中 `properties` 下的字段如果只在程序内部使用（启发式：字段名出现在 `_internal` / `_skip_llm` 等标记下却没加 `_` 前缀） | "字段名前加 `_` 前缀，会自动从 LLM schema 中剥离" |
| `pinyin_naming` | JC004 | 迁移现有 `check_pinyin_naming` 逻辑到统一接口（如果原实现不存在，留 stub 返回空列表 + TODO 注释） | "改用英文命名，例：chaxun → query" |

**实现要点**：
- 用 `ast` 模块解析 Python 源码（不要用正则匹配 Python 语法）
- 每个检查器单独一个文件，方便后续扩展
- 测试用 `tmp_path` fixture + 内联 source 字符串，不依赖外部样本文件

### 4.6 测试要求

每个检查器至少 3 个测试用例：

1. **正例**：含违规代码 → 必须报告 ≥ 1 个 LintFinding
2. **反例**：不含违规代码 → 必须报告 0 个 LintFinding
3. **suggestion 非空**：任意 finding 的 `suggestion` 字段必须非空字符串

### 4.7 修改 CI（仅 mypy 行）

打开 `.github/workflows/ci.yml`，定位到：

```yaml
    - name: Run type checking
      shell: bash
      run: |
        mypy packages/ || true
```

改为：

```yaml
    - name: Run type checking (strict for core packages)
      shell: bash
      run: |
        # Core packages must pass; outer packages allowed to fail for now.
        mypy packages/jay-agent-core/src packages/jay-llm/src
        mypy packages/jay-agent-tools/src packages/jay-coding-agent/src || true
```

**不要改 `Run linting` 步骤**、**不要改 build job / docs job**。

### 4.8 验收标准

```bash
# 1. 文件结构正确
ls packages/jay-agent-tools/src/jay_agent_tools/linters/
# 期望：__init__.py base.py no_print.py tool_envelope.py internal_field.py pinyin_naming.py

# 2. 测试通过
pytest packages/jay-agent-tools/tests/test_linters_*.py -v
# 期望：全部通过，覆盖率 ≥ 80%

# 3. 验证 LintFinding.suggestion 不为空（防止偷懒）
python -c "
from jay_agent_tools.linters.base import LintFinding
from pathlib import Path
try:
    LintFinding(file=Path('x'), line=1, code='T', message='m', suggestion='')
    print('FAIL: 空 suggestion 被接受')
except (ValueError, AssertionError):
    print('OK: 空 suggestion 被拒绝')
"
# 注意：这一步要求你在 LintFinding.__post_init__ 中 raise ValueError 拒绝空 suggestion

# 4. CI 文件改对了
grep -A1 "Run type checking" .github/workflows/ci.yml | grep -v "|| true" | head -5
# 期望：core 包那行没有 || true

# 5. 不要破坏现有测试
pytest packages/jay-agent-tools/tests/ -v --ignore=packages/jay-agent-tools/tests/test_linters_*.py 2>&1 | tail -3
# 期望：现有测试全部通过（或保持任务前的通过率）
```

### 4.9 边界

- **不要把 linters 接入 ruff**（这是后续工作，需要 ruff plugin 机制）
- **不要在 CI 里跑这些 linter**（暂时作为库函数提供，让 Agent 主动调用）
- **不要修复源码里被检出的违规**——只产出诊断
- **不要扩到 5 个以上**检查器
- pinyin_naming 如果在原代码中找不到完整实现，**只做 stub + TODO**，不要重新实现拼音词典

---

## 5. 最终联合验收

P0-1 + P0-2 + P0-3 全部完成后，写一份**地图自洽性测试**：

### 5.1 新建测试文件

`tests/test_knowledge_map.py`：

```python
"""验证 AGENTS.md 中 Knowledge Map 的每个条目都在 docs/agent-knowledge/ 有对应文档。"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = REPO_ROOT / "AGENTS.md"
KNOWLEDGE_DIR = REPO_ROOT / "docs" / "agent-knowledge"


def _extract_map_entries() -> list[str]:
    """从 AGENTS.md 的 Knowledge Map 段提取条目 ID."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    # 锁定 ## Knowledge Map 到下一个 ## 之间
    match = re.search(
        r"## Knowledge Map.*?(?=^## )", text, re.DOTALL | re.MULTILINE
    )
    assert match, "AGENTS.md 缺少 ## Knowledge Map 段"
    section = match.group(0)
    # 匹配 - **xxx** 形式
    return re.findall(r"^- \*\*([a-z0-9\-]+)\*\*", section, re.MULTILINE)


def test_agents_md_exists():
    assert AGENTS_MD.exists(), "AGENTS.md 不存在"


def test_agents_md_under_100_lines():
    lines = AGENTS_MD.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 100, f"AGENTS.md 超过 100 行（实际 {len(lines)} 行）"


def test_required_sections_present():
    text = AGENTS_MD.read_text(encoding="utf-8")
    for section in ("## Always Loaded", "## Knowledge Map", "## Known Pitfalls"):
        assert section in text, f"AGENTS.md 缺少 {section} 段"


def test_knowledge_map_has_8_entries():
    entries = _extract_map_entries()
    assert len(entries) == 8, f"Knowledge Map 应有 8 条，实际 {len(entries)}: {entries}"


@pytest.mark.parametrize("topic", _extract_map_entries())
def test_each_topic_doc_exists(topic):
    path = KNOWLEDGE_DIR / f"{topic}.md"
    assert path.exists(), f"地图条目 {topic} 缺少对应文档 {path}"


@pytest.mark.parametrize("topic", _extract_map_entries())
def test_each_topic_doc_has_required_sections(topic):
    text = (KNOWLEDGE_DIR / f"{topic}.md").read_text(encoding="utf-8")
    required = (
        "## 它解决什么问题",
        "## 核心机制",
        "## 关键代码锚点",
        "## 常见陷阱",
        "## 修改本机制时的检查清单",
        "## 相关",
    )
    for section in required:
        assert section in text, f"{topic}.md 缺少 {section} 段"
```

### 5.2 运行

```bash
pytest tests/test_knowledge_map.py -v
# 期望：全部通过
```

### 5.3 整体回归

```bash
# 不要破坏现有测试
pytest packages/jay-agent-core/tests/ packages/jay-agent-tools/tests/ -q
# 通过数应 ≥ 任务开始前的通过数
```

---

## 6. 完成后的产出清单（交付给人类审查）

完成所有任务后，输出一份简短报告（≤ 300 字）：

```
P0 改造完成报告
==============

新建文件：
- AGENTS.md（{N} 行）
- docs/agent-knowledge/{topic}.md × 8
- packages/jay-agent-tools/src/jay_agent_tools/linters/*.py × 6
- packages/jay-agent-tools/tests/test_linters_*.py × 4
- tests/test_knowledge_map.py

修改文件：
- .github/workflows/ci.yml（仅 mypy 行，从 || true 改为严格模式）

验收结果：
- tests/test_knowledge_map.py: {passed/failed}
- packages/jay-agent-tools/tests/test_linters_*.py: {passed/failed}
- ruff check：{passed/failed}
- 行数检查：AGENTS.md = {N} 行（≤ 100 ✓/✗）
- 现有测试无回归：{是/否}

未完成 / 待人类决策的事项：
- {如有}
```

---

## 7. 当任务过程中遇到这些情况时该怎么办

| 情况 | 处理方式 |
|---|---|
| `改进点详解.md` 里找不到某个 Pitfall 的具体描述 | 在 AGENTS.md 里写"详情：搜 git log"，不要编造细节 |
| 某个源码锚点对应的代码已被重构、行号对不上 | 用 `Grep` 重新定位关键字，写实际行号；如完全找不到，在文档里标注 `TODO: 锚点失效` |
| Linter 的 ast 解析对某些边界情况误报 | 在测试里加 `# noqa: JC00x` 注释逃逸机制，不要把规则改弱 |
| `pinyin_naming` 原实现完全找不到 | stub 返回 `[]`，文件头注释 `# TODO: 待 P1 完整实现拼音词典` |
| `mypy` 严格化后核心包真的有类型错误 | **不要为了让 CI 过而把 `|| true` 加回来**——把具体错误列在交付报告"待人类决策"段 |
| AGENTS.md 写到 95+ 行还没写完 | 砍 Known Pitfalls（保留 ≤ 3 条最关键的），保留全部 Knowledge Map 条目 |
| 时间不够 | 优先完成 P0-1 + P0-3（地图 + 知识库），P0-2 可只完成 base.py + 1 个检查器作为最小可交付 |

---

*本设计图配套 `HARNESS_EVALUATION.md` §四 P0 章节使用。*
*执行者：另一个 AI 助手。*
*范围：仅限 P0 三项任务，P1/P2 等下一份蓝图。*

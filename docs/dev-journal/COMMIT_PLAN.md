# Commit 拆分计划：P0 / P1 / P2 收尾后落库

> 上下文：本次工作树里堆积了三层东西——
> 1. **上一 session 的 P0 安全修复**（路径白名单 / Host 头 / safe_join 等）尚未提交
> 2. **上一 session 的 harness P0/P1 功能**（agents_md.py、进度跟踪、handoff、e2e 验证）尚未提交
> 3. **本 session 的 P1/P2**（单测补全 / server 模块化 / CHANGELOG+SECURITY / mypy+coverage gate / 异常吞没替换 / tool labels schema 化）
>
> 一次性大 commit 会让 reviewer 抓不住重点，回滚也粗。下面是按主题切分的 11 个 commit，每个独立可 review、可回滚。

## 推荐顺序

### Commit 1 — `chore: housekeeping (gitignore, gitattributes, HARNESS journal)`
零代码、纯仓库卫生，先做让后续 diff 干净。

```
.gitignore
.gitattributes
docs/dev-journal/HARNESS_EVALUATION.md
docs/dev-journal/HARNESS_P0_BLUEPRINT.md
docs/dev-journal/HARNESS_P0_REPORT.md
docs/dev-journal/HARNESS_P1_BLUEPRINT.md
docs/dev-journal/HARNESS_P1_REPORT.md
```

---

### Commit 2 — `feat(web-ui): apply P0 security hardening (path whitelist / Host header / safe_join)`
之前 session 的 P0 安全修复。**单独提**因为它涉及安全合规、最值得 reviewer 仔细看。

```
packages/jay-web-ui/src/jay_web_ui/attachments.py        (新)
packages/jay-web-ui/tests/test_attachments.py            (新)
packages/jay-web-ui/tests/test_safe_join.py              (新，含本 session 加的 symlink 测试)
packages/jay-web-ui/tests/test_workspace_whitelist.py    (新，含本 session 加的 3 个 edge case)
packages/jay-web-ui/tests/test_host_header.py            (新)
packages/jay-web-ui/tests/test_server.py                 (改 — Host header fixture)
```

> ⚠️ **取舍点**：这一组里 `_safe_join` / Host middleware 的实际代码在 commit 3 (server.py 拆分) 一起提；
> 可以拆也可以合，看你偏好。
> 如果 reviewer 偏好"安全代码 + 它的测试一起进"，那就把 commit 2 和 commit 3 中 server.py 相关的部分合并。

---

### Commit 3 — `refactor(web-ui): split 1685-line server.py into routes/ + security.py`

```
packages/jay-web-ui/src/jay_web_ui/security.py           (新)
packages/jay-web-ui/src/jay_web_ui/routes/__init__.py    (新)
packages/jay-web-ui/src/jay_web_ui/routes/llm.py         (新)
packages/jay-web-ui/src/jay_web_ui/routes/lifecycle.py   (新)
packages/jay-web-ui/src/jay_web_ui/routes/files.py       (新)
packages/jay-web-ui/src/jay_web_ui/routes/workspace.py   (新)
packages/jay-web-ui/src/jay_web_ui/routes/sessions.py    (新)
packages/jay-web-ui/src/jay_web_ui/routes/agents_md.py   (新)
packages/jay-web-ui/src/jay_web_ui/routes/skills_tools.py (新)
packages/jay-web-ui/src/jay_web_ui/routes/chat.py        (新)
packages/jay-web-ui/src/jay_web_ui/server.py             (改 — 1685 → ~430 行 + re-export)
```

**Commit message 要点**：

> Public ChatServer API and all HTTP routes are unchanged.
> Existing imports from `jay_web_ui.server` (`_safe_join`, `_check_workspace_path`, ...) still work via re-export.

---

### Commit 4 — `feat(llm): context window detection + Anthropic streaming tool_calls`

```
packages/jay-llm/src/jay_llm/__init__.py                  (改 — export detect_context_window)
packages/jay-llm/src/jay_llm/models.py                    (改)
packages/jay-llm/src/jay_llm/providers/__init__.py        (改)
packages/jay-llm/src/jay_llm/providers/anthropic.py       (改 — astream tool_calls fix)
packages/jay-llm/src/jay_llm/providers/openai.py          (改)
packages/jay-llm/src/jay_llm/context_window.py            (新)
packages/jay-llm/tests/test_anthropic_astream.py          (新)
packages/jay-llm/tests/test_context_window.py             (新 — 本 session 23 个用例)
packages/jay-llm/tests/test_client.py                     (改)
```

---

### Commit 5 — `feat(coding-agent): handoff document + agents_md generator`

```
packages/jay-coding-agent/src/jay_coding_agent/agents_md.py    (新)
packages/jay-coding-agent/src/jay_coding_agent/handoff.py      (改/新)
packages/jay-coding-agent/src/jay_coding_agent/agent.py        (改 — workspace switch + AGENTS.md)
packages/jay-coding-agent/src/jay_coding_agent/cli.py          (改)
packages/jay-coding-agent/tests/test_agents_md.py              (新)
packages/jay-coding-agent/tests/test_handoff.py                (新 — 含本 session 补的 5 个 helper 测试)
packages/jay-coding-agent/tests/test_agent.py                  (改)
packages/jay-coding-agent/tests/test_cli.py                    (改)
```

> 📝 **核对**：`git diff packages/jay-coding-agent/src/jay_coding_agent/handoff.py` 看一眼到底是改还是新——
> 本 session 没改这个文件，但 status 显示 modified 而 test_handoff.py 是 untracked，
> 说明上一 session 改了源码但测试是全新的。

---

### Commit 6 — `feat(agent-core): context utilization + share helpers`

```
packages/jay-agent-core/src/jay_agent_core/agent.py
packages/jay-agent-core/src/jay_agent_core/context.py
packages/jay-agent-core/src/jay_agent_core/share.py
```

---

### Commit 7 — `feat(web-ui): handoff / context / agents_md / sessions endpoints + frontend`
之前 session 的前端联动，体积大（app.js +700 行、style.css +275 行）。

```
packages/jay-web-ui/src/jay_web_ui/cli.py
packages/jay-web-ui/src/jay_web_ui/models.py
packages/jay-web-ui/src/jay_web_ui/static/app.js
packages/jay-web-ui/src/jay_web_ui/static/style.css
packages/jay-web-ui/src/jay_web_ui/templates/chat.html
packages/jay-web-ui/tests/test_cli.py
```

> 📝 **可选拆分**：如果你想精细 review，可以拆成
> "websocket handoff UI" / "sessions sidebar" / "agents.md modal" 三块；
> 但工作量大、收益看团队评审风格。

---

### Commit 8 — `refactor: replace silent except-pass with logger.exception/warning (P2-1)`
本 session 的代码净化。

```
packages/jay-web-ui/src/jay_web_ui/attachments.py            (logger import + 1 处)
packages/jay-web-ui/src/jay_web_ui/server.py                 (_record_to_session)
packages/jay-web-ui/src/jay_web_ui/routes/agents_md.py       (logger import + 1 处)
packages/jay-web-ui/src/jay_web_ui/routes/sessions.py        (logger import + 1 处)
packages/jay-web-ui/src/jay_web_ui/routes/lifecycle.py       (logger import + 1 处)
packages/jay-coding-agent/src/jay_coding_agent/agent.py      (logger import + 2 处)
packages/jay-coding-agent/src/jay_coding_agent/billing.py    (logger import + 1 处)
packages/jay-messenger/src/jay_messenger/bot.py              (logger import + 2 处)
packages/jay-messenger/src/jay_messenger/adapters/feishu.py  (logger import + 1 处)
packages/jay-agent-tools/src/jay_agent_tools/web/handlers.py (logger import + 2 处 — fallback chain 用 warning)
packages/jay-tui/src/jay_tui/advanced.py                     (logger import + 1 处 — UI 高频用 debug)
```

> ⚠️ **核对**：`git status` 还显示 `messenger/message.py`、`messenger/platform.py`、`tui/tests/test_chat.py`、`tui/tests/test_console.py`、`messenger/tests/test_feishu_compat.py`、`messenger/tests/test_slack_adapter.py` 也 modified；
> 如果不是本 session 的异常吞没主题改的，应拆到 commit 7 或单独一个 commit。
> `git diff <文件>` 看一下确认归类。

---

### Commit 9 — `feat(web-ui): schema-driven tool display labels (P2-2)`

```
packages/jay-web-ui/src/jay_web_ui/tool_labels.py         (新)
packages/jay-web-ui/tests/test_tool_labels.py            (新 — 13 用例)
packages/jay-web-ui/src/jay_web_ui/server.py             (改 — 删掉 19 行硬编码 _TOOL_LABELS dict)
```

---

### Commit 10 — `docs: add SECURITY.md, CHANGELOG.md; update README; clean stale AGENTS.md`

```
SECURITY.md                              (新)
CHANGELOG.md                             (新)
README.md                                (改)
AGENTS.md                                (删 — 旧版被 docs/dev-journal 内的新版替代)
docs/agent-knowledge/context-compression.md     (删)
docs/agent-knowledge/pinyin-naming.md           (删)
docs/agent-knowledge/resilience-chain.md        (删)
docs/agent-knowledge/ssrf-protection.md         (删)
docs/agent-knowledge/tool-lazy-loading.md       (删)
docs/agent-knowledge/tool-result-envelope.md    (删)
docs/agent-knowledge/web-ui-sse.md              (删)
docs/agent-knowledge/workspace-switch.md        (删)
examples/agent-core/basic_agent.py              (删)
```

---

### Commit 11 — `ci: fix pig→jay typo, add mypy --strict + coverage gates`

```
.github/workflows/ci.yml
```

**Commit message 要点**：
- 修复了之前装的是 `pig-*` 包（根本不是这个项目）的 typo
- 新增 strict typecheck step：`mypy --strict` 钉死 `context_window.py` / `handoff.py` / `security.py` 三个本轮硬化模块
- 新增 coverage 门禁：context_window/handoff `≥95%`，security `≥90%`（Linux 专属分支在 Windows runner 跳过）
- 整包 strict（jay-llm / jay-agent-core）暂留 `|| true` 作为渐进目标

---

## 顺序敏感事项（务必按此顺）

| 文件 | 被改的 commit |
|---|---|
| `packages/jay-web-ui/src/jay_web_ui/server.py` | 3 (routes 拆分) → 8 (logger.exception) → 9 (tool_labels) |

三次连续改同一文件 git 自然能合并，但务必按这个顺序提，否则 cherry-pick 时上下文对不上。

## 可合并的 commit

- **Commit 2 + Commit 3**：如果 reviewer 偏好"安全代码 + 它的容器（拆分后的 server.py）一起看更顺"，合成一个。分开是因为 routes/ 拆分本身和安全主题无关，纯结构改造。
- **Commit 5 + Commit 6 + Commit 7**：上一 session 的 harness P0/P1 功能，如果想"一次提完 harness 模块"也行，但 diff 会很大。

## 分阶段执行建议

如果你希望我**先帮你把零风险的 commit 跑了**，剩下你自己节奏来：

1. **Commit 1**（housekeeping）—— 100% 安全
2. **Commit 10**（docs SECURITY/CHANGELOG）—— 100% 安全，但需要确认 README.md 的改动是否本 session 的范畴
3. **Commit 11**（CI yml）—— 不影响代码运行，只动 CI
4. **Commit 9**（tool_labels）—— 本 session 的小型独立特性，自带测试

剩下 Commit 2-8 涉及上一 session 的产出和大型重构，你自己看哪些放 PR、哪些保本地。

---

## 验收脚本

每提一个 commit 后跑：

```bash
for pkg in jay-llm jay-coding-agent jay-agent-core jay-messenger jay-tui jay-web-ui; do
  echo "=== $pkg ==="
  python -m pytest packages/$pkg/tests/ --no-cov -q 2>&1 | tail -2
done
```

完整跑下来当前基线：**1105 测试通过**，6 个包全绿。

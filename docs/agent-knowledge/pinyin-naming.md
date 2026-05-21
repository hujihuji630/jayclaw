# Pinyin Naming（拼音命名检测）

> **何时读本文**：新工具命名、重构变量名时
> **关联源码**：`packages/jay-agent-tools/src/jay_agent_tools/web/handlers.py`、`packages/jay-agent-tools/src/jay_agent_tools/web/schemas.py`

## 它解决什么问题

中文开发者习惯把"用户"写成 `yonghu`、"查询"写成 `chaxun`。这种命名 LLM 既不认得（影响 Agent 自动重构能力），人类协作者读起来也割裂。本工具扫描代码 token，识别常见拼音词并给出英文等价物建议；新工具命名时也把这套词典作为禁忌列表。

## 核心机制

1. **词典 _PINYIN_WORDS**（约 80 词）：分用户/数据结构/操作/系统/业务/时间六类，覆盖中文项目里最常出现的拼音 token。
2. **词典 _SUGGESTIONS**：拼音 → 英文映射，如 `yonghu → user`、`chaxun → query`。
3. **token 提取**：`re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", code)` 抓出所有标识符；长度 < 3 的跳过避免误报。
4. **去重 + 建议**：同一 token 只报告一次，附上 `_SUGGESTIONS` 给的英文替代；不在词典里的拼音不会报告（保守策略，宁缺勿滥）。
5. **Tool schema**：注册为 `check_pinyin_naming(code, language=None)`，由 Agent 通过 `discover_tools(query="naming")` 发现并调用。

## 关键代码锚点

| 文件 | 行号 | 角色 |
|---|---|---|
| `packages/jay-agent-tools/src/jay_agent_tools/web/handlers.py` | L96-L117 | `_PINYIN_WORDS` 词典 |
| `packages/jay-agent-tools/src/jay_agent_tools/web/handlers.py` | L119-L140 | `_SUGGESTIONS` 拼音 → 英文映射 |
| `packages/jay-agent-tools/src/jay_agent_tools/web/handlers.py` | L309-L370 | `handle_check_pinyin_naming` handler |
| `packages/jay-agent-tools/src/jay_agent_tools/web/schemas.py` | L113-L130 | `check_pinyin_naming` schema |

## 常见陷阱

- **词典不是完备的**：拼音是开放集合，词典只覆盖高频词；少见拼音（`shoufa`、`kongzhi`）不会被检出。新增时优先按业务域增量。
- **大小写敏感**：当前实现按精确小写匹配，`YongHu` / `yongHu` 不会命中；如需支持需在 token 提取后小写化。
- **首字母拼音误报**：英文缩写如 `usr`、`pwd` 不在词典里所以安全，但有些短拼音（如 `yi`、`er`）刚好等于英文 `i`、`er` 词；当前用 `len < 3` 跳过来规避。
- **不区分上下文**：`hang` 既是中文"行"也可能是英文 `hang`（挂起）；当前一律建议改 `row`，需要人工复核。
- **不会自动重命名**：仅产出 finding 列表，重构动作仍需要 LLM 或人类决定。

## 修改本机制时的检查清单

- [ ] 词典新增条目时同时加 `_PINYIN_WORDS` 与 `_SUGGESTIONS`
- [ ] 新增条目时给一个真实代码示例验证不与英文单词冲突
- [ ] 修改后跑 `test_web_handlers.py` 中的 pinyin 测试，确认正反例都通过
- [ ] 输出格式与 ToolResult 包装一致

## 相关
- 关联条目：[tool-lazy-loading](tool-lazy-loading.md)

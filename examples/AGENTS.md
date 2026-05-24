# AGENTS.md

> 这是一份 **地图**，不是百科全书。Agent 启动只读本文，按需展开细节。
> 总行数控制在 100 行以内；条目过期请及时移除。

## Always Loaded（硬约束，永远遵守）

- Never commit .env or expose secrets; use .env.example as template
- Run Python scripts with `python <script>.py` from project root
- Check .env.example for required environment variables before running
- This is an examples project demonstrating various features and integrations
- Chinese language support is included (chinese_dev_tools_demo.py)

## Knowledge Map（按需加载）

- **web-ui** — when working with the web interface or start_web_ui.py
- **skills** — when extending agent capabilities via skills/
- **extensions** — when adding custom extensions or reading extension-example.py
- **sessions** — when managing conversation state or reading session-example.py
- **message-queue** — when working with async messaging patterns
- **output-modes** — when customizing output formats

## Known Pitfalls（历史教训，每条 1 行）

> 每次踩坑后追加一行。格式：`YYYY-MM: 简述`

_(empty — 会话结束后由 /agents-summarize 写入)_

## How to Use This Map

- Agent 启动时本文件自动注入到 system prompt
- 维护：会话结束时 Agent 会询问是否将经验追加到本文件
- 在 REPL 中可用 `/agents-init` 重新生成、`/agents-summarize` 立即追加

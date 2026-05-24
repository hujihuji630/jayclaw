"""Skills + tools dynamic-add endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request


def register(server) -> None:
    """Mount skill+tool endpoints onto ``server.app``."""

    @server.app.get("/api/skills")
    async def get_skills():
        if server.agent and hasattr(server.agent, "skills"):
            skills = [
                {"name": s.name, "description": getattr(s, "description", "")}
                for s in (server.agent.skills or [])
            ]
            return {"skills": skills}
        return {"skills": []}

    @server.app.get("/api/tools")
    async def get_tools():
        core_agent = (
            server.agent.agent
            if (server.agent and hasattr(server.agent, "agent"))
            else server.agent
        )
        if core_agent and hasattr(core_agent, "registry_enhanced"):
            schemas = core_agent.registry_enhanced.get_schemas()
            tools = [
                {"name": s["function"]["name"],
                 "description": s["function"].get("description", "")}
                for s in schemas
            ]
            return {"tools": tools}
        if server.agent and hasattr(server.agent, "tools"):
            tools = [
                {"name": t.name if hasattr(t, "name") else str(t),
                 "description": getattr(t, "description", "")}
                for t in (server.agent.tools or [])
            ]
            return {"tools": tools}
        return {"tools": []}

    @server.app.post("/api/tools")
    async def add_tool(request: Request):
        """动态添加工具（通过 Python 代码）"""
        body = await request.json()
        code = body.get("code", "").strip()
        if not code:
            return {"status": "error", "error": "code is required"}

        if "@tool" not in code:
            return {"status": "error", "error": "代码必须包含 @tool 装饰器"}
        if "def " not in code:
            return {"status": "error", "error": "代码必须定义函数"}

        try:
            from jay_agent_core.tools import tool
            namespace = {"tool": tool}
            exec(code, namespace)

            core_agent = (
                server.agent.agent if hasattr(server.agent, "agent") else server.agent
            )
            added_tools = []
            for name, obj in namespace.items():
                if hasattr(obj, "__class__") and obj.__class__.__name__ == "Tool":
                    if not hasattr(obj, "name") or not obj.name:
                        return {"status": "error", "error": "工具必须有名称"}
                    if not hasattr(obj, "func") or not callable(obj.func):
                        return {"status": "error", "error": "工具必须有可调用函数"}

                    core_agent.add_tool(obj)

                    if hasattr(core_agent, "registry_enhanced"):
                        def make_handler(t):
                            async def _handler(args, user_id=None, meta=None, cancel=None):
                                from jay_agent_core.tools.base import ToolResult
                                try:
                                    result = await t.aexecute(**args)
                                    return ToolResult(ok=True, data=result)
                                except Exception as e:
                                    return ToolResult(ok=False, error=str(e))
                            return _handler

                        core_agent.registry_enhanced.register(
                            name=obj.name,
                            handler=make_handler(obj),
                            schema=obj.to_openai_schema(),
                            is_core=True,
                            timeout=60.0,
                        )

                    added_tools.append(obj.name)

            if not added_tools:
                return {"status": "error", "error": "未找到有效的工具定义"}

            return {"status": "ok", "tools": added_tools}
        except SyntaxError as e:
            return {"status": "error", "error": f"语法错误: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"执行失败: {e}"}

    @server.app.post("/api/skills")
    async def add_skill(request: Request):
        """动态添加 Skill（保存 SKILL.md）"""
        body = await request.json()
        name = body.get("name", "").strip()
        content = body.get("content", "").strip()

        if not name or not content:
            return {"status": "error", "error": "name and content are required"}

        if not name.replace("-", "").replace("_", "").isalnum():
            return {"status": "error", "error": "Skill 名称只能包含字母、数字、下划线和连字符"}
        if len(name) > 50:
            return {"status": "error", "error": "Skill 名称不能超过 50 字符"}

        if not content.startswith("#"):
            return {"status": "error", "error": "Skill 内容必须以 Markdown 标题开头（# 标题）"}
        if len(content) < 20:
            return {"status": "error", "error": "Skill 内容过短，至少需要 20 字符"}

        try:
            from jay_agent_core.skills import Skill

            skills_dir = Path.cwd() / ".claude" / "skills" / name
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skills_dir / "SKILL.md"
            skill_file.write_text(content, encoding="utf-8")

            skill = Skill(name=name, path=skill_file, content=content)

            if not skill.title:
                return {"status": "error", "error": "无法解析 Skill 标题"}

            core_agent = (
                server.agent.agent if hasattr(server.agent, "agent") else server.agent
            )
            if hasattr(core_agent, "skill_manager"):
                core_agent.skill_manager.skills[name] = skill

            return {"status": "ok", "skill": name, "path": str(skill_file)}
        except Exception as e:
            return {"status": "error", "error": f"保存失败: {e}"}

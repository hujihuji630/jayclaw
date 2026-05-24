"""AGENTS.md init / summarize / cancel endpoints."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import Request

logger = logging.getLogger(__name__)


def register(server) -> None:
    """Mount AGENTS.md endpoints onto ``server.app``."""

    def _workspace_path() -> Path:
        ws = Path.cwd()
        if server.agent and hasattr(server.agent, "workspace"):
            ws = Path(server.agent.workspace)
        return ws

    def _agents_md_path(workspace: Path) -> Path:
        return workspace / "AGENTS.md"

    def _no_init_marker(workspace: Path) -> Path:
        return workspace / ".jayclaw" / ".no-agents-md"

    @server.app.get("/api/agents-md/status")
    async def agents_md_status():
        """Tell the frontend whether to show the init modal."""
        workspace = _workspace_path()
        agents_md = _agents_md_path(workspace)
        never_marker = _no_init_marker(workspace).exists()
        exists = agents_md.is_file()
        return {
            "workspace": str(workspace),
            "exists": exists,
            "never_marker": never_marker,
            "suggest_prompt": (not exists) and (not never_marker),
            "has_history": len(server.history) > 0,
        }

    @server.app.post("/api/agents-md/init")
    async def agents_md_init(request: Request):
        """Body: {action: 'generate' | 'skip' | 'never'}."""
        body = await request.json()
        action = (body.get("action") or "").strip().lower()
        workspace = _workspace_path()

        if action == "skip":
            return {"status": "ok", "action": "skip"}

        if action == "never":
            try:
                marker = _no_init_marker(workspace)
                marker.parent.mkdir(exist_ok=True)
                marker.write_text("", encoding="utf-8")
                return {
                    "status": "ok",
                    "action": "never",
                    "marker": str(marker),
                }
            except OSError as exc:
                return {"status": "error", "error": f"无法写入标记: {exc}"}

        if action != "generate":
            return {"status": "error", "error": f"未知 action: {action}"}

        try:
            from jay_coding_agent.agents_md import generate_initial
        except ImportError as exc:
            return {"status": "error", "error": f"agents_md 模块不可用: {exc}"}

        llm = server._resolve_llm()
        if llm is None:
            return {"status": "error", "error": "未配置 LLM"}

        if server._agents_md_task and not server._agents_md_task.done():
            return {"status": "error", "error": "已有 AGENTS.md 任务在运行，请先取消"}

        server._agents_md_task = asyncio.create_task(generate_initial(workspace, llm))
        try:
            path = await server._agents_md_task
        except asyncio.CancelledError:
            return {"status": "cancelled"}
        except Exception as exc:
            return {"status": "error", "error": f"生成失败: {exc}"}
        finally:
            server._agents_md_task = None

        # Refresh system prompt so the new AGENTS.md takes effect this session
        try:
            if (
                server.agent
                and hasattr(server.agent, "_get_system_prompt")
                and hasattr(server.agent, "agent")
                and hasattr(server.agent.agent, "system_prompt")
            ):
                new_prompt = server.agent._get_system_prompt()
                server.agent.agent.system_prompt = new_prompt
                history = getattr(server.agent.agent, "history", None)
                if history and getattr(history[0], "role", None) == "system":
                    from jay_llm import Message
                    history[0] = Message(role="system", content=new_prompt)
        except Exception:
            logger.exception("system-prompt refresh after AGENTS.md init failed")

        try:
            rel = path.relative_to(workspace)
        except ValueError:
            rel = path

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""

        return {
            "status": "ok",
            "action": "generated",
            "path": str(path),
            "relative_path": str(rel),
            "content": content,
        }

    @server.app.post("/api/agents-md/summarize-preview")
    async def agents_md_summarize_preview():
        """Run LLM summary and return the proposed new content + diff (no write yet)."""
        workspace = _workspace_path()
        target = _agents_md_path(workspace)
        if not target.is_file():
            return {"status": "error", "error": "工作目录下没有 AGENTS.md，请先初始化"}

        if not server.history:
            return {"status": "error", "error": "本次会话尚无对话内容可总结"}

        try:
            from jay_coding_agent.agents_md import append_session_summary
        except ImportError as exc:
            return {"status": "error", "error": f"agents_md 模块不可用: {exc}"}

        llm = server._resolve_llm()
        if llm is None:
            return {"status": "error", "error": "未配置 LLM"}

        if server._agents_md_task and not server._agents_md_task.done():
            return {"status": "error", "error": "已有 AGENTS.md 任务在运行，请先取消"}

        history_payload = [
            {"role": m.role, "content": m.content} for m in server.history
        ]
        server._agents_md_task = asyncio.create_task(
            append_session_summary(workspace, llm, history_payload, target)
        )
        try:
            new_content, diff, parsed = await server._agents_md_task
        except asyncio.CancelledError:
            return {"status": "cancelled"}
        except FileNotFoundError as exc:
            return {"status": "error", "error": str(exc)}
        except Exception as exc:
            return {"status": "error", "error": f"总结失败: {exc}"}
        finally:
            server._agents_md_task = None

        new_pitfalls = parsed.get("new_pitfalls") or []
        new_constraints = parsed.get("new_constraints") or []

        try:
            rel = target.relative_to(workspace)
        except ValueError:
            rel = target

        return {
            "status": "ok",
            "path": str(target),
            "relative_path": str(rel),
            "new_content": new_content,
            "diff": diff,
            "new_pitfalls": new_pitfalls,
            "new_constraints": new_constraints,
            "no_changes": not (new_pitfalls or new_constraints),
        }

    @server.app.post("/api/agents-md/summarize-write")
    async def agents_md_summarize_write(request: Request):
        """Body: {content: <full AGENTS.md content from preview step>}."""
        body = await request.json()
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            return {"status": "error", "error": "content 必填"}
        if len(content.encode("utf-8")) > 256 * 1024:
            return {"status": "error", "error": "content 过大（>256KiB），拒绝写入"}

        workspace = _workspace_path().resolve()
        target = (workspace / "AGENTS.md").resolve()
        try:
            target.relative_to(workspace)
        except ValueError:
            return {"status": "error", "error": "目标路径逃逸出工作目录"}
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return {"status": "error", "error": f"写入失败: {exc}"}

        try:
            rel = target.relative_to(workspace)
        except ValueError:
            rel = target
        return {"status": "ok", "path": str(target), "relative_path": str(rel)}

    @server.app.post("/api/agents-md/cancel")
    async def agents_md_cancel():
        """Cancel the in-flight AGENTS.md task (init or summarize-preview)."""
        task = server._agents_md_task
        if task and not task.done():
            task.cancel()
            return {"status": "ok", "cancelled": True}
        return {"status": "ok", "cancelled": False}

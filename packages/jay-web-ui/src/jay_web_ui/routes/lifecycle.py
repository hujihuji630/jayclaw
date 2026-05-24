"""Lifecycle: interrupt, cancel, status, compact, history, fork, session rename."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import Request

logger = logging.getLogger(__name__)


def register(server) -> None:
    """Mount lifecycle endpoints onto ``server.app``."""

    @server.app.post("/api/interrupt")
    async def interrupt(request: Request):
        body = await request.json()
        message = body.get("message", "").strip()
        if not message:
            return {"status": "error", "error": "message is required"}

        core_agent = (
            server.agent.agent
            if (server.agent and hasattr(server.agent, "agent"))
            else server.agent
        )
        if not core_agent or not hasattr(core_agent, "message_queue"):
            return {"status": "error", "error": "Agent does not support message queue"}

        core_agent.message_queue.add_steering(message)
        return {"status": "ok", "queued": "steering"}

    @server.app.post("/api/cancel")
    async def cancel():
        if server._cancel_event:
            server._cancel_event.set()
        if server._active_task and not server._active_task.done():
            server._active_task.cancel()
        return {"status": "ok"}

    @server.app.get("/api/status")
    async def get_status():
        return {
            "generating": server._active_task is not None and not server._active_task.done()
        }

    @server.app.post("/api/compact")
    async def compact_context():
        """Compress the agent's context window using LLM summarization."""
        core_agent = server._resolve_core_agent()
        if not core_agent or not hasattr(core_agent, "history"):
            return {"status": "error", "error": "No agent history available"}

        from jay_agent_core.context import compress_level3, compress_level2

        messages = core_agent.history
        if not messages:
            return {"status": "ok", "before": 0, "after": 0}

        before = len(messages)
        llm = server._resolve_llm()

        msg_dicts = []
        for m in messages:
            entry = {"role": m.role, "content": m.content or ""}
            meta = getattr(m, "metadata", None) or {}
            if "tool_calls" in meta:
                entry["tool_calls"] = meta["tool_calls"]
            if "name" in meta:
                entry["name"] = meta["name"]
            msg_dicts.append(entry)

        try:
            compressed_dicts = await compress_level3(msg_dicts, llm)
        except Exception:
            compressed_dicts = compress_level2(msg_dicts)

        from jay_llm import Message as LLMMessage
        new_history = []
        for d in compressed_dicts:
            meta = {}
            if "tool_calls" in d:
                meta["tool_calls"] = d["tool_calls"]
            if "name" in d:
                meta["name"] = d["name"]
            new_history.append(
                LLMMessage(
                    role=d["role"],
                    content=d.get("content") or "",
                    metadata=meta or None,
                )
            )
        core_agent.history = new_history
        after = len(new_history)
        return {"status": "ok", "before": before, "after": after}

    @server.app.get("/api/history")
    async def get_history():
        return {"messages": [msg.model_dump() for msg in server.history]}

    @server.app.delete("/api/history")
    async def clear_history():
        """Clear chat history (saves current session first)."""
        if server.agent and hasattr(server.agent, "session"):
            try:
                if server.agent.session.tree.entries:
                    server.agent.session.save()
            except Exception:
                logger.exception("session save before clear_history failed; clearing anyway")
        server.history.clear()
        if server.agent:
            server.agent.clear_history()
        return {"status": "ok"}

    @server.app.post("/api/session/rename")
    async def rename_session(request: Request):
        body = await request.json()
        name = (body.get("name") or "").strip()
        if not name:
            return {"status": "error", "error": "name is required"}
        if server.agent and hasattr(server.agent, "session"):
            server.agent.session.name = name
            return {"status": "ok", "name": name}
        return {"status": "error", "error": "No active session"}

    @server.app.post("/api/fork")
    async def fork_session(request: Request):
        """Fork current session with rollback options."""
        from jay_web_ui.models import ChatMessage  # noqa: F401  (kept for type hints)

        body = await request.json()
        mode = body.get("mode", "session_only")
        fork_index = body.get("fork_index", -1)

        workspace = Path.cwd()
        if server.agent and hasattr(server.agent, "workspace"):
            workspace = Path(server.agent.workspace)

        result_parts = []

        if mode in ("code_only", "both"):
            import subprocess
            branch_name = f"fork-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            try:
                subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    cwd=str(workspace),
                    check=True,
                    capture_output=True,
                )
                result_parts.append(f"已创建分支 {branch_name}")
            except subprocess.CalledProcessError as e:
                return {"status": "error", "error": f"Git 操作失败: {e.stderr.decode()}"}

        retained_messages: list[dict] = []
        if mode in ("session_only", "both"):
            try:
                from jay_agent_core.session import Session

                agent_session = None
                if server.agent and hasattr(server.agent, "session"):
                    agent_session = server.agent.session
                if agent_session and agent_session.tree.entries:
                    original_path = agent_session.save()
                    result_parts.append(f"原会话已保存: {original_path.name}")

                    if 0 <= fork_index < len(server.history):
                        retained = list(server.history[: fork_index + 1])
                    else:
                        retained = []

                    new_session = Session(workspace=str(workspace))
                    server.agent.session = new_session
                    server.history.clear()
                    for msg in retained:
                        server.history.append(msg)
                        server._record_to_session(msg.role, msg.content)
                    retained_messages = [
                        {"role": m.role, "content": m.content} for m in retained
                    ]
                    result_parts.append("已开启新对话")
                else:
                    result_parts.append("会话无消息，跳过")
            except ImportError:
                result_parts.append("Session 模块不可用")

        return {
            "status": "ok",
            "detail": "; ".join(result_parts) or "完成",
            "retained": retained_messages,
        }

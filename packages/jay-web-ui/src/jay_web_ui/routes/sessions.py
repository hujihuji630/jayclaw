"""Session list/load/delete + handoff + context-utilization endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, Request

from jay_web_ui.models import ChatMessage

logger = logging.getLogger(__name__)


def register(server) -> None:
    """Mount session/handoff endpoints onto ``server.app``."""

    @server.app.get("/api/context")
    async def get_context_utilization():
        """Return context window utilization based on the agent's real history."""
        try:
            from jay_agent_core.context import compute_utilization
        except ImportError:
            return {"available": False}

        llm = server._resolve_llm()
        max_tokens = server._resolve_context_window(llm)
        messages, model = server._agent_messages_for_tokens()
        util = compute_utilization(messages, max_tokens, model=model)
        return {
            "available": True,
            "current_tokens": util.current_tokens,
            "max_tokens": util.max_tokens,
            "ratio": util.ratio,
            "percent": util.percent,
            "zone": util.zone,
            "should_prompt_user": util.should_prompt_user,
        }

    @server.app.post("/api/handoff")
    async def create_handoff():
        """Generate a handoff document for session continuation (LLM-based)."""
        try:
            from jay_coding_agent.handoff import (
                generate_handoff_via_llm,
                generate_handoff,
                extract_handoff_data_from_history,
            )
            from jay_agent_core.context import compute_utilization
        except ImportError as exc:
            return {"status": "error", "error": f"Handoff module not available: {exc}"}

        workspace = Path.cwd()
        if server.agent and hasattr(server.agent, "workspace"):
            workspace = Path(server.agent.workspace)

        messages, model = server._agent_messages_for_tokens()
        progress_path = workspace / ".jayclaw" / "progress.json"

        llm = server._resolve_llm()
        max_tokens = server._resolve_context_window(llm)

        ratio = 0.0
        try:
            util = compute_utilization(messages, max_tokens, model=model)
            ratio = util.ratio
        except Exception:
            logger.exception("compute_utilization failed; using ratio=0.0 in handoff")

        try:
            if llm is not None and messages:
                transcript_msgs = [m for m in messages if m.get("role") != "system"]
                path = await generate_handoff_via_llm(
                    llm,
                    transcript_msgs,
                    workspace,
                    ratio,
                    progress_path=progress_path if progress_path.exists() else None,
                )
                mode = "llm"
            else:
                transcript_msgs = [m for m in messages if m.get("role") != "system"]
                data = extract_handoff_data_from_history(
                    transcript_msgs,
                    progress_path=progress_path if progress_path.exists() else None,
                )
                path = generate_handoff(data, workspace, ratio)
                mode = "template"
        except Exception as exc:
            return {"status": "error", "error": f"Handoff generation failed: {exc}"}

        try:
            rel = path.relative_to(workspace)
        except ValueError:
            rel = path
        return {
            "status": "ok",
            "path": str(path),
            "relative_path": str(rel),
            "mode": mode,
        }

    @server.app.get("/api/sessions")
    async def list_sessions():
        """List saved sessions from .sessions/ directory."""
        try:
            from jay_agent_core.session_manager import SessionManager
        except ImportError:
            return {"sessions": []}

        workspace = Path.cwd()
        if server.agent and hasattr(server.agent, "workspace"):
            workspace = Path(server.agent.workspace)

        mgr = SessionManager(workspace)
        sessions = mgr.list_sessions(limit=20)
        return {"sessions": [
            {"name": s.session_name, "modified": s.modified.isoformat(),
             "entries": s.entries, "path": str(s.path)}
            for s in sessions
        ]}

    @server.app.post("/api/sessions/load")
    async def load_session(request: Request):
        """Load a saved session into the current conversation."""
        body = await request.json()
        session_path = body.get("path", "").strip()
        if not session_path:
            return {"status": "error", "error": "path is required"}

        try:
            from jay_agent_core.session import Session
        except ImportError:
            return {"status": "error", "error": "Session module not available"}

        p = Path(session_path)
        if not p.exists():
            return {"status": "error", "error": "Session file not found"}

        session = Session.load(p)
        conversation = session.get_current_conversation()

        server.history.clear()
        messages = []
        idx = 0
        for entry in conversation:
            if entry.role in ("user", "assistant"):
                # Legacy session entries lack an id on disk; assign a stable
                # synthetic id so frontend truncate/edit operations have a key.
                entry_id = getattr(entry, "id", None) or f"legacy-{idx}"
                msg = ChatMessage(id=entry_id, role=entry.role, content=entry.content)
                server.history.append(msg)
                messages.append({"id": entry_id, "role": entry.role, "content": entry.content})
                idx += 1

        if server.agent and hasattr(server.agent, "session"):
            server.agent.session = session

        return {"status": "ok", "messages": messages}

    @server.app.delete("/api/sessions")
    async def delete_session(request: Request):
        """Delete a saved session file."""
        body = await request.json()
        session_path = (body.get("path") or "").strip()
        if not session_path:
            return {"status": "error", "error": "path is required"}
        p = Path(session_path)
        if not p.is_file():
            return {"status": "error", "error": "会话文件不存在"}
        try:
            p.unlink()
            return {"status": "ok"}
        except OSError as e:
            return {"status": "error", "error": str(e)}

    @server.app.get("/api/sessions/{session_id}/export.md")
    async def export_session_md(session_id: str):
        """Export the current chat session as a Markdown download."""
        from datetime import datetime

        from fastapi.responses import Response

        if session_id != "current":
            # v1.1 only supports in-memory current session export.
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

        messages = [
            {"role": m.role, "content": m.content}
            for m in server.history
            if m.role in ("user", "assistant")
        ]

        lines = [
            "# JayClaw chat export",
            f"_{datetime.now().isoformat(timespec='seconds')}_",
            "",
        ]
        for m in messages:
            heading = "你" if m["role"] == "user" else "JayClaw"
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(m["content"])
            lines.append("")

        body = "\n".join(lines)
        name = "chat"
        if server.agent and hasattr(server.agent, "session"):
            try:
                name = server.agent.session.name or "chat"
            except Exception:
                pass
        date_part = datetime.now().strftime("%Y%m%d")
        filename = f"chat-{name}-{date_part}.md"
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

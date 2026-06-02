"""Chat (SSE) + WebSocket endpoints.

These two endpoints are mounted by the registrar below but the heavy
``_stream_response`` / ``_vision_fallback`` machinery still lives on
``ChatServer`` because it needs deep access to many private attributes.
"""

from __future__ import annotations

import asyncio

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse

from jay_web_ui.models import ChatMessage, ChatRequest


def register(server) -> None:
    """Mount chat endpoints onto ``server.app``."""

    @server.app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Serve chat UI."""
        return server.templates.TemplateResponse(
            request=request,
            name="chat.html",
            context={
                "title": server.title,
                "theme": server.theme,
                "model": (
                    server.llm.config.model
                    if server.llm
                    else (server.agent.llm.config.model if server.agent else "unknown")
                ),
            },
        )

    @server.app.post("/api/chat")
    async def chat(request: ChatRequest):
        """Handle chat message with SSE streaming."""
        return StreamingResponse(
            server._stream_response(request.message, request.attachments),
            media_type="text/event-stream",
        )

    @server.app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time chat."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                message = data.get("message", "")
                if not message:
                    continue

                server.history.append(ChatMessage(role="user", content=message))
                server._record_to_session("user", message)

                await websocket.send_json({"type": "received"})

                if server.agent:
                    if hasattr(server.agent, "agent") and hasattr(server.agent.agent, "arun"):
                        core_agent = server.agent.agent
                    elif hasattr(server.agent, "arun"):
                        core_agent = server.agent
                    else:
                        response = server.agent.run(message)
                        content = response.content
                        await websocket.send_json({"type": "token", "content": content})
                        core_agent = None

                    if core_agent:
                        token_queue: asyncio.Queue = asyncio.Queue()
                        orig_token = getattr(core_agent, "on_token", None)
                        core_agent.on_token = lambda t: token_queue.put_nowait(t)

                        task = asyncio.create_task(core_agent.arun(message))
                        content = ""
                        try:
                            while not task.done():
                                while not token_queue.empty():
                                    token = token_queue.get_nowait()
                                    await websocket.send_json(
                                        {"type": "token", "content": token}
                                    )
                                    content += token
                                await asyncio.sleep(0.02)
                            # Drain remaining
                            while not token_queue.empty():
                                token = token_queue.get_nowait()
                                await websocket.send_json(
                                    {"type": "token", "content": token}
                                )
                                content += token
                            task.result()
                        finally:
                            core_agent.on_token = orig_token
                elif server.llm:
                    if hasattr(server.llm, "stream"):
                        full_content = ""
                        for chunk in server.llm.stream(message):
                            await websocket.send_json(
                                {"type": "token", "content": chunk.content}
                            )
                            full_content += chunk.content
                        content = full_content
                    else:
                        response = server.llm.complete(message)
                        content = response.content
                        await websocket.send_json(
                            {"type": "token", "content": content}
                        )
                else:
                    content = "No LLM configured"
                    await websocket.send_json({"type": "token", "content": content})

                if content:
                    server.history.append(ChatMessage(role="assistant", content=content))
                    server._record_to_session("assistant", content)

                await websocket.send_json({"type": "done"})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            await websocket.send_json({"type": "error", "error": str(e)})

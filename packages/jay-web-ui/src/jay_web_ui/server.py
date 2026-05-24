"""Chat server with FastAPI.

The HTTP routes have been split into ``jay_web_ui.routes`` submodules — this
file holds the ``ChatServer`` class, the Host-header anti-DNS-rebinding
middleware, and the streaming machinery that the chat route delegates to.

Path-validation primitives (``_safe_join``, ``_check_workspace_path``, etc.)
live in ``jay_web_ui.security`` and are re-exported here for backward
compatibility with tests that imported them from this module before the split.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .attachments import build_multimodal_content, process_attachments
from .models import ChatMessage, StreamChunk
from .routes import (
    agents_md as agents_md_routes,
    chat as chat_routes,
    files as files_routes,
    lifecycle as lifecycle_routes,
    llm as llm_routes,
    mcp as mcp_routes,
    messages as messages_routes,
    sessions as sessions_routes,
    skills_tools as skills_tools_routes,
    workspace as workspace_routes,
)
# Re-exported for backward compatibility — tests import these from jay_web_ui.server.
from .security import (  # noqa: F401
    SYSTEM_PATH_DENY_PREFIXES,
    _allowed_workspace_roots,
    _check_workspace_path,
    _is_system_path,
    _is_under_allowed_root,
    _safe_join,
)

logger = logging.getLogger(__name__)


class ChatServer:
    """Chat server with web UI."""

    def __init__(
        self,
        llm=None,
        agent=None,
        title: str = "Chat",
        port: int = 8000,
        host: str = "127.0.0.1",
        cors: bool = False,
        cors_allow_origins: list[str] | None = None,
        theme: dict | None = None,
    ):
        """Initialize chat server.

        Args:
            llm: LLM instance (from jay-llm)
            agent: Agent instance (from jay-agent-core)
            title: Page title
            port: Server port
            host: Server host
            cors: Enable CORS
            cors_allow_origins: Explicit list of allowed origins when ``cors`` is
                True. When omitted, defaults to ``[f"http://{host}:{port}"]`` to
                avoid the unsafe ``*`` + credentials combination.
            theme: UI theme customization
        """
        if not llm and not agent:
            raise ValueError("Must provide either llm or agent")

        self.llm = llm
        self.agent = agent
        self.title = title
        self.port = port
        self.host = host
        self.theme = theme or {}

        # Vision model fallback (user-configured)
        self.vision_model: str | None = None

        self.app = FastAPI(title=title)

        # Anti-DNS-rebinding: when bound to localhost, refuse requests whose
        # Host header doesn't claim to be us. Without this, an attacker page
        # at evil.com could resolve evil.com → 127.0.0.1 (DNS rebinding) and
        # then drive our /api/* endpoints from any browser tab. We don't run
        # this when host is 0.0.0.0 / a real LAN IP because there the user
        # is explicitly opting into broader exposure.
        if host in ("127.0.0.1", "localhost", "::1"):
            allowed_hosts = {
                f"127.0.0.1:{port}",
                f"localhost:{port}",
                f"[::1]:{port}",
                # Browsers strip the default port for some schemes; tolerate
                # the port-less form too.
                "127.0.0.1",
                "localhost",
                "[::1]",
            }

            @self.app.middleware("http")
            async def _enforce_host_header(request: Request, call_next):
                host_header = (request.headers.get("host") or "").lower()
                if host_header and host_header not in allowed_hosts:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=400,
                        content={"detail": f"unexpected Host header: {host_header}"},
                    )
                return await call_next(request)

        # Enable CORS if requested. Never combine "*" with credentials — that
        # combination is rejected by browsers and signals a misconfigured policy.
        if cors:
            origins = cors_allow_origins or [f"http://{host}:{port}"]
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
            )

        self.base_dir = Path(__file__).parent
        self.templates = Jinja2Templates(directory=str(self.base_dir / "templates"))
        self.app.mount(
            "/static",
            StaticFiles(directory=str(self.base_dir / "static")),
            name="static",
        )

        self.history: list[ChatMessage] = []

        # Active generation state
        self._cancel_event: asyncio.Event | None = None
        self._active_task: asyncio.Task | None = None

        # Active AGENTS.md task (init / summarize) — cancelled by /api/agents-md/cancel
        self._agents_md_task: asyncio.Task | None = None

        self._setup_routes()

    def _setup_routes(self):
        """Mount HTTP routes from the ``routes/`` submodules.

        Order is purely cosmetic — FastAPI dispatch is path-based, not
        registration-order — but grouping by concern keeps logs/openapi readable.
        """
        llm_routes.register(self)
        lifecycle_routes.register(self)
        messages_routes.register(self)
        files_routes.register(self)
        workspace_routes.register(self)
        sessions_routes.register(self)
        agents_md_routes.register(self)
        skills_tools_routes.register(self)
        mcp_routes.register(self)
        chat_routes.register(self)

    def _resolve_core_agent(self):
        """Return the inner jay_agent_core Agent (carries the full history)."""
        if not self.agent:
            return None
        if hasattr(self.agent, "agent") and getattr(self.agent.agent, "history", None) is not None:
            return self.agent.agent
        if getattr(self.agent, "history", None) is not None:
            return self.agent
        return None

    def _resolve_llm(self):
        """Return the underlying LLM instance, prefering the agent's LLM."""
        if self.agent:
            if hasattr(self.agent, "agent") and hasattr(self.agent.agent, "llm"):
                return self.agent.agent.llm
            if hasattr(self.agent, "llm"):
                return self.agent.llm
        return self.llm

    def _agent_messages_for_tokens(self) -> tuple[list[dict], str | None]:
        """Serialize the agent's real history (incl. system / tool_calls / tool results).

        Falls back to ``self.history`` if the agent isn't reachable.
        Returns (messages, model_name_for_tokenizer).
        """
        core_agent = self._resolve_core_agent()
        llm = self._resolve_llm()
        model = getattr(getattr(llm, "config", None), "model", None)

        if core_agent is None:
            messages = [{"role": m.role, "content": m.content} for m in self.history]
            return messages, model

        out: list[dict] = []
        for msg in core_agent.history:
            entry: dict = {"role": msg.role, "content": msg.content or ""}
            metadata = getattr(msg, "metadata", None) or {}
            if "tool_calls" in metadata:
                entry["tool_calls"] = metadata["tool_calls"]
            if "name" in metadata:
                entry["name"] = metadata["name"]
            out.append(entry)
        return out, model

    def _resolve_context_window(self, llm) -> int:
        """Return the model's input-context window size in tokens.

        Order: env override > model family table > provider default > 8192.
        Never confuses ``config.max_tokens`` (output cap) with the context window.
        """
        try:
            from jay_llm import detect_context_window
        except ImportError:
            return 8192

        cfg = getattr(llm, "config", None) if llm else None
        model = getattr(cfg, "model", None)
        provider = getattr(cfg, "provider", None)
        return detect_context_window(model, provider)

    def _record_to_session(self, role: str, content: str) -> None:
        """Persist a message to the agent's session tree (auto-saves to .sessions/)."""
        if not self.agent or not hasattr(self.agent, "session"):
            return
        try:
            self.agent.session.add_message(role, content)
        except Exception:
            logger.exception("session.add_message failed (role=%s); message not persisted", role)

    async def _vision_fallback(self, multimodal_content: list, user_message: str) -> str:
        """Use the vision model to directly answer the user's question about images.

        Instead of describing images then passing to main model, the vision model
        handles the full request in one call — much faster, no tool loop.
        For large image sets, batches them and combines responses.
        """
        from jay_llm import LLM, Message as LLMMessage

        llm = self._resolve_llm()
        cfg = llm.config

        vision_llm = LLM(
            provider=cfg.provider,
            api_key=cfg.api_key,
            model=self.vision_model,
            base_url=cfg.base_url,
            temperature=cfg.temperature,
            timeout=300,
        )

        image_blocks = [b for b in multimodal_content if b.get("type") == "image_url"]
        text_blocks = [b for b in multimodal_content if b.get("type") == "text"]
        user_text = "\n".join(b.get("text", "") for b in text_blocks) or user_message

        # If <= 5 images, send all at once
        if len(image_blocks) <= 5:
            messages = [LLMMessage(role="user", content=multimodal_content)]
            try:
                response = await vision_llm.achat(messages)
                return response.content
            except Exception as e:
                return f"[视觉模型调用失败: {e}]"

        # For many images, batch them and ask for content extraction per batch,
        # then do a final call to answer the user's question.
        MAX_PER_BATCH = 5
        all_extractions: list[str] = []

        for i in range(0, len(image_blocks), MAX_PER_BATCH):
            batch = image_blocks[i:i + MAX_PER_BATCH]
            batch_num = i // MAX_PER_BATCH + 1
            total_batches = (len(image_blocks) + MAX_PER_BATCH - 1) // MAX_PER_BATCH

            prompt = (
                f"（第 {batch_num}/{total_batches} 批，共 {len(image_blocks)} 页）"
                "请提取图片中的所有文字、数据和结构，直接输出内容。"
            )
            messages = [LLMMessage(
                role="user",
                content=[{"type": "text", "text": prompt}] + batch,
            )]
            try:
                resp = await vision_llm.achat(messages)
                all_extractions.append(resp.content)
            except Exception as e:
                all_extractions.append(f"[第 {batch_num} 批解析失败: {e}]")

        extracted = "\n\n".join(all_extractions)
        final_prompt = f"{user_text}\n\n--- 以下是文档内容 ---\n{extracted}"
        try:
            resp = await vision_llm.achat([LLMMessage(role="user", content=final_prompt)])
            return resp.content
        except Exception as e:
            return f"文档内容提取结果：\n\n{extracted}\n\n[最终分析调用失败: {e}]"

    async def _stream_response(self, message: str, attachments: list | None = None) -> AsyncIterator[str]:
        """Stream response as SSE."""
        self.history.append(ChatMessage(role="user", content=message))
        self._record_to_session("user", message)

        workspace = Path.cwd()
        if self.agent and hasattr(self.agent, "workspace"):
            workspace = Path(self.agent.workspace)

        agent_content: str | list = message
        if attachments:
            image_blocks, text_content = process_attachments(attachments, workspace)
            agent_content = build_multimodal_content(message, image_blocks, text_content)

        # Vision model fallback
        vision_used = False
        if isinstance(agent_content, list) and self.vision_model:
            llm = self._resolve_llm()
            current_model = getattr(getattr(llm, "config", None), "model", None)
            if current_model and self.vision_model != current_model:
                vision_used = True

        self._cancel_event = asyncio.Event()

        try:
            yield self._format_sse(StreamChunk(type="start"))

            if vision_used:
                img_count = sum(1 for b in agent_content if b.get("type") == "image_url")
                yield self._format_sse(StreamChunk(
                    type="status",
                    status=f"⚙ 调用视觉模型 {self.vision_model} 处理 {img_count} 张图片...",
                ))
                assistant_msg = ChatMessage(role="assistant", content="")
                yield self._format_sse(StreamChunk(
                    type="message_start", id=assistant_msg.id, role="assistant",
                ))
                content = await self._vision_fallback(agent_content, message)
                yield self._format_sse(StreamChunk(type="token", content=content))
                assistant_msg.content = content
                self.history.append(assistant_msg)
                self._record_to_session("assistant", content)
                yield self._format_sse(StreamChunk(
                    type="message_end", id=assistant_msg.id,
                ))
                yield self._format_sse(StreamChunk(type="done"))
                return

            yield self._format_sse(StreamChunk(type="status", status="正在思考..."))

            assistant_msg = ChatMessage(role="assistant", content="")
            yield self._format_sse(StreamChunk(
                type="message_start", id=assistant_msg.id, role="assistant",
            ))

            if self.agent:
                content = ""
                core_agent = self.agent.agent if hasattr(self.agent, "agent") else self.agent

                status_queue: asyncio.Queue = asyncio.Queue()

                # Display labels are now derived from each tool's schema
                # description (first clause), with optional curated overrides
                # in ``jay_web_ui.tool_labels._OVERRIDES``. New tools that
                # register through registry_enhanced show up automatically.
                from .tool_labels import build_tool_label_map, resolve_label

                tool_labels: dict[str, str] = {}
                try:
                    if hasattr(core_agent, "registry_enhanced"):
                        tool_labels = build_tool_label_map(
                            core_agent.registry_enhanced.get_schemas()
                        )
                except Exception:
                    logger.exception("tool-label map build failed; falling back to raw names")

                def on_tool_start(tool_name, tool_args):
                    label = resolve_label(tool_labels, tool_name) or f"调用 {tool_name}"
                    status_queue.put_nowait(f"⚙ {label}...")

                def on_tool_end(tool_name, result):
                    label = resolve_label(tool_labels, tool_name)
                    status_queue.put_nowait(f"✓ {label} 完成")

                orig_start = core_agent.on_tool_start
                orig_end = core_agent.on_tool_end
                core_agent.on_tool_start = on_tool_start
                core_agent.on_tool_end = on_tool_end

                yield self._format_sse(StreamChunk(type="status", status="正在分析请求..."))

                self._active_task = asyncio.create_task(core_agent.arun(agent_content))

                try:
                    cancelled = False
                    while not self._active_task.done():
                        if self._cancel_event.is_set():
                            self._active_task.cancel()
                            cancelled = True
                            break
                        while not status_queue.empty():
                            status = status_queue.get_nowait()
                            yield self._format_sse(StreamChunk(type="status", status=status))
                        await asyncio.sleep(0.05)

                    if cancelled:
                        yield self._format_sse(StreamChunk(type="status", status="⛔ 已中止"))
                        yield self._format_sse(StreamChunk(type="done"))
                        return

                    while not status_queue.empty():
                        status = status_queue.get_nowait()
                        yield self._format_sse(StreamChunk(type="status", status=status))

                    response = self._active_task.result()
                    content = response.content
                finally:
                    self._active_task = None
                    core_agent.on_tool_start = orig_start
                    core_agent.on_tool_end = orig_end

                yield self._format_sse(StreamChunk(type="token", content=content))

            elif self.llm:
                content = ""
                if hasattr(self.llm, "stream"):
                    for chunk in self.llm.stream(message):
                        if self._cancel_event.is_set():
                            yield self._format_sse(StreamChunk(type="status", status="⛔ 已中止"))
                            yield self._format_sse(StreamChunk(type="done"))
                            return
                        yield self._format_sse(StreamChunk(type="token", content=chunk.content))
                        content += chunk.content
                        await asyncio.sleep(0)
                else:
                    response = self.llm.complete(message)
                    content = response.content
                    yield self._format_sse(StreamChunk(type="token", content=content))
            else:
                content = "No LLM or agent configured"
                yield self._format_sse(StreamChunk(type="token", content=content))

            if content:
                assistant_msg.content = content
                self.history.append(assistant_msg)
                self._record_to_session("assistant", content)
                yield self._format_sse(StreamChunk(
                    type="message_end", id=assistant_msg.id,
                ))

            yield self._format_sse(StreamChunk(type="done"))

        except asyncio.CancelledError:
            yield self._format_sse(StreamChunk(type="status", status="⛔ 已中止"))
            yield self._format_sse(StreamChunk(type="done"))
        except Exception as e:
            yield self._format_sse(StreamChunk(type="error", error=str(e)))
        finally:
            self._cancel_event = None
            self._active_task = None

    def _format_sse(self, chunk: StreamChunk) -> str:
        """Format chunk as SSE."""
        return f"data: {chunk.model_dump_json()}\n\n"

    def run(self, **kwargs):
        """Run the server."""
        import uvicorn

        uvicorn.run(
            self.app,
            host=kwargs.get("host", self.host),
            port=kwargs.get("port", self.port),
            **{k: v for k, v in kwargs.items() if k not in ["host", "port"]},
        )

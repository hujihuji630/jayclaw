"""Chat server with FastAPI."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import ChatMessage, ChatRequest, StreamChunk


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
        theme: dict | None = None,
    ):
        """Initialize chat server.

        Args:
            llm: LLM instance (from py-ai)
            agent: Agent instance (from py-agent-core)
            title: Page title
            port: Server port
            host: Server host
            cors: Enable CORS
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

        # Create FastAPI app
        self.app = FastAPI(title=title)

        # Enable CORS if requested
        if cors:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Setup templates and static files
        self.base_dir = Path(__file__).parent
        self.templates = Jinja2Templates(directory=str(self.base_dir / "templates"))
        self.app.mount(
            "/static",
            StaticFiles(directory=str(self.base_dir / "static")),
            name="static",
        )

        # Conversation history
        self.history: list[ChatMessage] = []

        # Active generation state
        self._cancel_event: asyncio.Event | None = None
        self._active_task: asyncio.Task | None = None

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup API routes."""

        @self.app.get("/api/models")
        async def get_models():
            """获取当前 API 可用的模型列表"""
            # Get LLM config from agent or direct
            llm = None
            if self.agent:
                if hasattr(self.agent, 'agent') and hasattr(self.agent.agent, 'llm'):
                    llm = self.agent.agent.llm
                elif hasattr(self.agent, 'llm'):
                    llm = self.agent.llm
            elif self.llm:
                llm = self.llm

            if not llm or not hasattr(llm, 'config'):
                return {"models": [], "current": "unknown"}

            try:
                import httpx
                base_url = (llm.config.base_url or "https://api.openai.com/v1").rstrip("/")
                headers = {"Authorization": f"Bearer {llm.config.api_key}"}
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{base_url}/models", headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    models.sort()
                    return {"models": models, "current": llm.config.model}
            except Exception as e:
                return {"models": [llm.config.model], "current": llm.config.model, "error": str(e)}

        @self.app.post("/api/model")
        async def set_model(request: Request):
            """切换当前使用的模型"""
            body = await request.json()
            new_model = body.get("model", "").strip()
            if not new_model:
                return {"status": "error", "error": "model is required"}

            # Get LLM from agent or direct
            llm = None
            if self.agent:
                if hasattr(self.agent, 'agent') and hasattr(self.agent.agent, 'llm'):
                    llm = self.agent.agent.llm
                elif hasattr(self.agent, 'llm'):
                    llm = self.agent.llm
            elif self.llm:
                llm = self.llm

            if not llm:
                return {"status": "error", "error": "No LLM configured"}

            # Recreate LLM with new model
            from jay_llm import LLM
            new_llm = LLM(
                provider=llm.config.provider,
                api_key=llm.config.api_key,
                model=new_model,
                base_url=llm.config.base_url,
                temperature=llm.config.temperature,
            )

            # Update the LLM reference
            if self.agent:
                if hasattr(self.agent, 'agent') and hasattr(self.agent.agent, 'llm'):
                    self.agent.agent.llm = new_llm
                elif hasattr(self.agent, 'llm'):
                    self.agent.llm = new_llm
            elif self.llm:
                self.llm = new_llm

            return {"status": "ok", "model": new_model}

        @self.app.post("/api/interrupt")
        async def interrupt(request: Request):
            """Inject a steering message into the running agent."""
            body = await request.json()
            message = body.get("message", "").strip()
            if not message:
                return {"status": "error", "error": "message is required"}

            core_agent = self.agent.agent if (self.agent and hasattr(self.agent, 'agent')) else self.agent
            if not core_agent or not hasattr(core_agent, 'message_queue'):
                return {"status": "error", "error": "Agent does not support message queue"}

            core_agent.message_queue.add_steering(message)
            return {"status": "ok", "queued": "steering"}

        @self.app.post("/api/cancel")
        async def cancel():
            """Cancel the current agent generation."""
            if self._cancel_event:
                self._cancel_event.set()
            if self._active_task and not self._active_task.done():
                self._active_task.cancel()
            return {"status": "ok"}

        @self.app.get("/api/status")
        async def get_status():
            """Return whether agent is currently generating."""
            return {"generating": self._active_task is not None and not self._active_task.done()}

        @self.app.get("/", response_class=HTMLResponse)
        async def home(request: Request):
            """Serve chat UI."""
            return self.templates.TemplateResponse(
                request=request,
                name="chat.html",
                context={
                    "title": self.title,
                    "theme": self.theme,
                    "model": self.llm.config.model if self.llm else (self.agent.llm.config.model if self.agent else "unknown"),
                },
            )

        @self.app.post("/api/chat")
        async def chat(request: ChatRequest):
            """Handle chat message with SSE streaming."""
            return StreamingResponse(
                self._stream_response(request.message),
                media_type="text/event-stream",
            )

        @self.app.get("/api/history")
        async def get_history():
            """Get chat history."""
            return {"messages": [msg.model_dump() for msg in self.history]}

        @self.app.delete("/api/history")
        async def clear_history():
            """Clear chat history."""
            self.history.clear()
            if self.agent:
                self.agent.clear_history()
            return {"status": "ok"}

        @self.app.post("/api/upload")
        async def upload_file(file: UploadFile = File(...)):
            """Handle file upload."""
            try:
                content = await file.read()
                filename = file.filename

                # Store uploaded file (simplified - production would store properly)
                upload_dir = Path(".uploads")
                upload_dir.mkdir(exist_ok=True)

                file_path = upload_dir / filename
                file_path.write_bytes(content)

                return {
                    "status": "ok",
                    "filename": filename,
                    "size": len(content),
                    "path": str(file_path),
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}

        @self.app.get("/api/config")
        async def get_config():
            """返回当前 LLM 配置（隐藏 API Key）"""
            # Get LLM from agent or direct
            llm = None
            if self.agent:
                if hasattr(self.agent, 'agent') and hasattr(self.agent.agent, 'llm'):
                    llm = self.agent.agent.llm
                elif hasattr(self.agent, 'llm'):
                    llm = self.agent.llm
            elif self.llm:
                llm = self.llm

            if not llm or not hasattr(llm, 'config'):
                return {}

            cfg = llm.config
            return {
                "provider": cfg.provider,
                "model": cfg.model,
                "base_url": cfg.base_url or "（默认）",
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens or "（不限）",
            }

        @self.app.get("/api/skills")
        async def get_skills():
            if self.agent and hasattr(self.agent, 'skills'):
                skills = [
                    {"name": s.name, "description": getattr(s, 'description', '')}
                    for s in (self.agent.skills or [])
                ]
                return {"skills": skills}
            return {"skills": []}

        @self.app.get("/api/workspace")
        async def get_workspace():
            if self.agent and hasattr(self.agent, 'workspace'):
                return {"workspace": str(self.agent.workspace)}
            return {"workspace": str(Path.cwd())}

        @self.app.post("/api/workspace")
        async def set_workspace(request: Request):
            body = await request.json()
            new_path = body.get("path", "").strip()
            if not new_path:
                return {"status": "error", "error": "path is required"}
            try:
                if hasattr(self.agent, 'change_workspace'):
                    resolved = self.agent.change_workspace(new_path)
                elif hasattr(self.agent, 'agent') and hasattr(self.agent.agent, 'change_workspace'):
                    resolved = self.agent.change_workspace(new_path)
                else:
                    return {"status": "error", "error": "Agent does not support workspace change"}
                return {"status": "ok", "workspace": resolved}
            except ValueError as e:
                return {"status": "error", "error": str(e)}

        @self.app.get("/api/browse/native")
        async def browse_native():
            """Open a native OS directory picker and return the chosen path."""
            import subprocess, sys, json, asyncio

            # Run tkinter in a separate Python subprocess so it gets its own main thread
            script = (
                "import tkinter as tk; from tkinter import filedialog; "
                "root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', True); "
                "path = filedialog.askdirectory(title='选择工作目录'); "
                "root.destroy(); "
                "import json, sys; print(json.dumps(path or ''))"
            )
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
                path = json.loads(stdout.decode().strip())
                if path:
                    return {"status": "ok", "path": path}
                return {"status": "cancelled"}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        @self.app.get("/api/browse")
        async def browse_dirs(path: str = ""):
            """Return subdirectories of a given path for the directory picker."""
            import os
            if not path:
                # Return drive roots on Windows, / on Unix
                if os.name == 'nt':
                    import string
                    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
                    return {"path": "", "dirs": drives, "parent": None}
                else:
                    path = "/"
            p = Path(path)
            if not p.exists() or not p.is_dir():
                return {"error": f"Not a directory: {path}"}
            try:
                dirs = sorted(
                    [str(child) for child in p.iterdir()
                     if child.is_dir() and not child.name.startswith('.')],
                    key=lambda x: x.lower()
                )
            except PermissionError:
                dirs = []
            parent = str(p.parent) if p.parent != p else None
            return {"path": str(p), "dirs": dirs, "parent": parent}

        @self.app.get("/api/tools")
        async def get_tools():
            core_agent = self.agent.agent if (self.agent and hasattr(self.agent, 'agent')) else self.agent
            if core_agent and hasattr(core_agent, 'registry_enhanced'):
                schemas = core_agent.registry_enhanced.get_schemas()
                tools = [
                    {"name": s["function"]["name"], "description": s["function"].get("description", "")}
                    for s in schemas
                ]
                return {"tools": tools}
            if self.agent and hasattr(self.agent, 'tools'):
                tools = [
                    {"name": t.name if hasattr(t, 'name') else str(t),
                     "description": getattr(t, 'description', '')}
                    for t in (self.agent.tools or [])
                ]
                return {"tools": tools}
            return {"tools": []}

        @self.app.post("/api/tools")
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

                core_agent = self.agent.agent if hasattr(self.agent, 'agent') else self.agent
                added_tools = []
                for name, obj in namespace.items():
                    if hasattr(obj, '__class__') and obj.__class__.__name__ == 'Tool':
                        if not hasattr(obj, 'name') or not obj.name:
                            return {"status": "error", "error": "工具必须有名称"}
                        if not hasattr(obj, 'func') or not callable(obj.func):
                            return {"status": "error", "error": "工具必须有可调用函数"}

                        # Add to legacy registry
                        core_agent.add_tool(obj)

                        # Also register to registry_enhanced so arun() can use it
                        if hasattr(core_agent, 'registry_enhanced'):
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

        @self.app.post("/api/skills")
        async def add_skill(request: Request):
            """动态添加 Skill（保存 SKILL.md）"""
            body = await request.json()
            name = body.get("name", "").strip()
            content = body.get("content", "").strip()

            if not name or not content:
                return {"status": "error", "error": "name and content are required"}

            # 验证 name 格式
            if not name.replace("-", "").replace("_", "").isalnum():
                return {"status": "error", "error": "Skill 名称只能包含字母、数字、下划线和连字符"}
            if len(name) > 50:
                return {"status": "error", "error": "Skill 名称不能超过 50 字符"}

            # 验证 content 结构
            if not content.startswith("#"):
                return {"status": "error", "error": "Skill 内容必须以 Markdown 标题开头（# 标题）"}
            if len(content) < 20:
                return {"status": "error", "error": "Skill 内容过短，至少需要 20 字符"}

            try:
                from pathlib import Path
                from jay_agent_core.skills import Skill

                # Save to .claude/skills/
                skills_dir = Path.cwd() / ".claude" / "skills" / name
                skills_dir.mkdir(parents=True, exist_ok=True)
                skill_file = skills_dir / "SKILL.md"
                skill_file.write_text(content, encoding="utf-8")

                # Load skill
                skill = Skill(name=name, path=skill_file, content=content)

                # 验证 skill 解析成功
                if not skill.title:
                    return {"status": "error", "error": "无法解析 Skill 标题"}

                # Add to agent's skill manager
                core_agent = self.agent.agent if hasattr(self.agent, 'agent') else self.agent
                if hasattr(core_agent, 'skill_manager'):
                    core_agent.skill_manager.skills[name] = skill

                return {"status": "ok", "skill": name, "path": str(skill_file)}
            except Exception as e:
                return {"status": "error", "error": f"保存失败: {e}"}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time chat."""
            await websocket.accept()

            try:
                while True:
                    # Receive message
                    data = await websocket.receive_json()
                    message = data.get("message", "")

                    if not message:
                        continue

                    # Add to history
                    self.history.append(ChatMessage(role="user", content=message))

                    # Send acknowledgment
                    await websocket.send_json({"type": "received"})

                    # Get response
                    if self.agent:
                        if hasattr(self.agent, 'agent') and hasattr(self.agent.agent, 'arun'):
                            response = await self.agent.agent.arun(message)
                        elif hasattr(self.agent, 'arun'):
                            response = await self.agent.arun(message)
                        else:
                            response = self.agent.run(message)
                        content = response.content
                    elif self.llm:
                        # Check if streaming
                        if hasattr(self.llm, "stream"):
                            # Stream via WebSocket
                            full_content = ""
                            for chunk in self.llm.stream(message):
                                await websocket.send_json(
                                    {
                                        "type": "token",
                                        "content": chunk.content,
                                    }
                                )
                                full_content += chunk.content
                            content = full_content
                        else:
                            response = self.llm.complete(message)
                            content = response.content
                            await websocket.send_json(
                                {
                                    "type": "token",
                                    "content": content,
                                }
                            )
                    else:
                        content = "No LLM configured"
                        await websocket.send_json(
                            {
                                "type": "token",
                                "content": content,
                            }
                        )

                    # Add to history
                    if content:
                        self.history.append(ChatMessage(role="assistant", content=content))

                    # Send done
                    await websocket.send_json({"type": "done"})

            except WebSocketDisconnect:
                pass
            except Exception as e:
                await websocket.send_json({"type": "error", "error": str(e)})

    async def _stream_response(self, message: str) -> AsyncIterator[str]:
        """Stream response as SSE."""
        self.history.append(ChatMessage(role="user", content=message))

        self._cancel_event = asyncio.Event()

        try:
            yield self._format_sse(StreamChunk(type="start"))
            yield self._format_sse(StreamChunk(type="status", status="正在思考..."))

            if self.agent:
                content = ""
                core_agent = self.agent.agent if hasattr(self.agent, 'agent') else self.agent

                # Use asyncio.Queue to receive tool events from arun()
                status_queue: asyncio.Queue = asyncio.Queue()

                _TOOL_LABELS = {
                    "run_command": "执行命令",
                    "search_web": "搜索网络",
                    "read_webpage": "读取网页",
                    "read_file": "读取文件",
                    "write_file": "写入文件",
                    "list_files": "列出文件",
                    "grep_files": "搜索文件内容",
                    "find_files": "查找文件",
                    "generate_code": "生成代码",
                    "explain_code": "分析代码",
                    "think": "深度思考",
                    "plan": "制定计划",
                    "git_status": "查看 Git 状态",
                    "git_diff": "查看代码差异",
                    "git_commit": "提交代码",
                    "search_zhihu": "搜索知乎",
                    "translate_to_english": "翻译内容",
                    "discover_tools": "加载工具",
                    "get_current_time": "获取时间",
                }

                def on_tool_start(tool_name, tool_args):
                    label = _TOOL_LABELS.get(tool_name, f"调用 {tool_name}")
                    status_queue.put_nowait(f"⚙ {label}...")

                def on_tool_end(tool_name, result):
                    label = _TOOL_LABELS.get(tool_name, tool_name)
                    status_queue.put_nowait(f"✓ {label} 完成")

                orig_start = core_agent.on_tool_start
                orig_end = core_agent.on_tool_end
                core_agent.on_tool_start = on_tool_start
                core_agent.on_tool_end = on_tool_end

                yield self._format_sse(StreamChunk(type="status", status="正在分析请求..."))

                # Run arun() as a background task so we can yield status events concurrently
                self._active_task = asyncio.create_task(core_agent.arun(message))

                try:
                    cancelled = False
                    while not self._active_task.done():
                        if self._cancel_event.is_set():
                            self._active_task.cancel()
                            cancelled = True
                            break
                        # Drain status queue
                        while not status_queue.empty():
                            status = status_queue.get_nowait()
                            yield self._format_sse(StreamChunk(type="status", status=status))
                        await asyncio.sleep(0.05)

                    if cancelled:
                        yield self._format_sse(StreamChunk(type="status", status="⛔ 已中止"))
                        yield self._format_sse(StreamChunk(type="done"))
                        return

                    # Drain any remaining status events
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
                self.history.append(ChatMessage(role="assistant", content=content))

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
        """Format chunk as SSE.

        Args:
            chunk: Stream chunk

        Returns:
            SSE formatted string
        """
        return f"data: {chunk.model_dump_json()}\n\n"

    def run(self, **kwargs):
        """Run the server.

        Args:
            **kwargs: Arguments for uvicorn.run
        """
        import uvicorn

        uvicorn.run(
            self.app,
            host=kwargs.get("host", self.host),
            port=kwargs.get("port", self.port),
            **{k: v for k, v in kwargs.items() if k not in ["host", "port"]},
        )

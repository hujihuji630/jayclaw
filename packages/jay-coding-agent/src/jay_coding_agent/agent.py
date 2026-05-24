"""Coding agent with file operations and code generation."""

import logging
from pathlib import Path

from jay_agent_core import (
    Agent,
    ContextManager,
    ExtensionManager,
    PromptManager,
    Session,
    SessionManager,
    SkillManager,
)
from jay_agent_core.context import compress_messages, CompressionConfig
from jay_agent_core.token_counter import count_tokens
from jay_agent_core.tools import Tool
from jay_llm import LLM, detect_context_window
from jay_tui import ChatUI, InteractivePrompt

from .billing import CostTracker
from .file_reference import FileReferenceParser
from .resilience import create_profile_manager_from_env, get_profile_status
from .tools import CodeTools, FileTools, ShellTools

logger = logging.getLogger(__name__)


def get_context_window(model: str, provider: str | None = None) -> int:
    """Resolve a model's context window size.

    Thin wrapper over :func:`jay_llm.detect_context_window` kept for backward
    compatibility with previous callers in this package.
    """
    return detect_context_window(model, provider)


class CodingAgent:
    """Interactive coding agent with file and code tools."""

    def __init__(
        self,
        llm: LLM | None = None,
        workspace: str = ".",
        verbose: bool = True,
        session_name: str | None = None,
        session_path: Path | None = None,
        enable_extensions: bool = True,
        enable_skills: bool = True,
        enable_resilience: bool = True,
        enable_cost_tracking: bool = True,
    ):
        """Initialize coding agent.

        Args:
            llm: LLM client
            workspace: Working directory
            verbose: Enable verbose output
            session_name: Session name for auto-save
            session_path: Path to load existing session
            enable_extensions: Enable extension system
            enable_skills: Enable skills system
            enable_resilience: Enable resilience (API key rotation, fallback)
            enable_cost_tracking: Enable cost tracking
        """
        self.workspace = Path(workspace).resolve()
        self.llm = llm or LLM()
        self.verbose = verbose

        # Initialize resilience (ProfileManager)
        self.profile_manager = None
        if enable_resilience:
            self.profile_manager = create_profile_manager_from_env()
            if self.profile_manager and verbose:
                status = get_profile_status(self.profile_manager)
                print(f"✓ Resilience enabled: {status['available_profiles']} API keys available")

        # Initialize cost tracking
        self.cost_tracker = None
        if enable_cost_tracking:
            self.cost_tracker = CostTracker(self.workspace)
            if verbose:
                print("✓ Cost tracking enabled")

        # Initialize session
        if session_path and session_path.exists():
            self.session = Session.load(session_path)
            print(f"✓ Loaded session: {self.session.name}")
        else:
            self.session = Session(
                name=session_name or "coding-session",
                workspace=str(self.workspace),
                auto_save=True,
            )

        # Register web tools to global registry
        try:
            from jay_agent_tools.web import register_tools
            registered = register_tools()
            if verbose and registered:
                print(f"✓ Registered {len(registered)} web tools: {', '.join(registered)}")
        except ImportError:
            if verbose:
                print("⚠ Web tools not available (jay_agent_tools not installed)")

        # Initialize tools
        file_tools = FileTools(str(self.workspace))
        code_tools = CodeTools()
        shell_tools = ShellTools()

        # Get all tool methods (descriptor protocol auto-binds self)
        tools = []
        for tool_instance in [file_tools, code_tools, shell_tools]:
            for attr_name in dir(tool_instance):
                attr = getattr(tool_instance, attr_name)
                if isinstance(attr, Tool):
                    tools.append(attr)

        # Initialize context manager (needed by _get_system_prompt)
        self.context_manager = ContextManager(self.workspace)

        # Initialize skill manager
        self.skill_manager = None
        if enable_skills:
            self.skill_manager = SkillManager()
            self.skill_manager.discover_skills([])
            if len(self.skill_manager) > 0:
                print(f"✓ Loaded {len(self.skill_manager)} skills")

        _llm = self.llm
        _config = CompressionConfig()

        def _compress_fn(messages):
            model = _llm.config.model
            provider = getattr(_llm.config, "provider", None)
            max_tokens = get_context_window(model, provider)
            text = " ".join(str(m) for m in messages)
            current_tokens = count_tokens(text, model=model)
            return compress_messages(messages, current_tokens, max_tokens, _config)

        # Create agent
        self.agent = Agent(
            name="CodingAgent",
            llm=self.llm,
            tools=tools,
            system_prompt=self._get_system_prompt(),
            verbose=verbose,
            profile_manager=self.profile_manager,
            billing_hook=self.cost_tracker,
            compress_fn=_compress_fn,
            max_rounds=30,
        )

        # Register core tools (think/plan/discover_tools/get_current_time) to registry_enhanced
        from jay_agent_core.tools import HANDLERS as CORE_HANDLERS, TOOL_SCHEMAS as CORE_SCHEMAS, TOOL_BUDGETS
        for schema in CORE_SCHEMAS:
            tool_name = schema["function"]["name"]
            handler = CORE_HANDLERS.get(tool_name)
            if handler:
                budget = TOOL_BUDGETS.get(tool_name, {})
                self.agent.registry_enhanced.register(
                    name=tool_name,
                    handler=handler,
                    schema=schema,
                    is_core=True,
                    timeout=float(budget.get("timeout", 30)),
                    max_retries=budget.get("max_retries", 0),
                )

        # Register web tools to registry_enhanced as core tools (always visible to LLM)
        try:
            from jay_agent_tools.web import HANDLERS as WEB_HANDLERS, TOOL_SCHEMAS as WEB_SCHEMAS
            for schema in WEB_SCHEMAS:
                tool_name = schema["function"]["name"]
                handler = WEB_HANDLERS.get(tool_name)
                if handler:
                    self.agent.registry_enhanced.register(
                        name=tool_name,
                        handler=handler,
                        schema=schema,
                        is_core=True,
                        timeout=30.0,
                    )
            if verbose:
                print(f"✓ Web tools registered to enhanced registry ({len(WEB_SCHEMAS)} tools)")
        except ImportError:
            pass

        # Register file/code/shell Tool objects into registry_enhanced
        def make_handler(t):
            async def _handler(args, user_id=None, meta=None, cancel=None):
                from jay_agent_core.tools.base import ToolResult
                try:
                    result = await t.aexecute(**args)
                    return ToolResult(ok=True, data=result)
                except Exception as e:
                    return ToolResult(ok=False, error=str(e))
            return _handler

        for tool_obj in tools:
            self.agent.registry_enhanced.register(
                name=tool_obj.name,
                handler=make_handler(tool_obj),
                schema=tool_obj.to_openai_schema(),
                is_core=True,
                timeout=60.0,
            )

        # Register delegate tool with LLM and read-only tools injected
        self._register_delegate_tool(tools)

        # Initialize MCP
        from jay_agent_core.mcp import MCPManager
        self.mcp_manager = MCPManager(self.workspace)
        self._init_mcp_sync()

        # Initialize extension manager
        self.extension_manager = None
        if enable_extensions:
            self.extension_manager = ExtensionManager(self.agent)
            self._load_extensions()

        # Initialize prompt manager
        self.prompt_manager = PromptManager()
        self.prompt_manager.discover_prompts([])
        if len(self.prompt_manager) > 0:
            print(f"✓ Loaded {len(self.prompt_manager)} prompt templates")

        # Initialize file reference parser
        self.file_ref_parser = FileReferenceParser(self.workspace)

        # Create UI
        self.ui = ChatUI(title="Coding Agent", show_timestamps=False)

    def _load_extensions(self):
        """Load extensions from standard directories."""
        if not self.extension_manager:
            return

        # Standard extension paths
        ext_paths = [
            self.workspace / ".jayclaw" / "extensions",
            self.workspace / ".pi" / "extensions",
            Path.home() / ".jayclaw" / "extensions",
        ]

        for path in ext_paths:
            if path.exists():
                self.extension_manager.load_from_directory(path)

    def _init_mcp_sync(self):
        """Load MCP config and start servers synchronously."""
        import asyncio
        from jay_agent_core.mcp import load_mcp_config

        configs = load_mcp_config(self.workspace)
        if not configs:
            return

        async def _start():
            await self.mcp_manager.load_and_start()
            registered = self.mcp_manager.register_tools(self.agent.registry_enhanced)
            return registered

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return
            registered = loop.run_until_complete(_start())
        except RuntimeError:
            registered = asyncio.run(_start())

        if registered and self.verbose:
            print(f"✓ MCP: {len(registered)} tools from {len(self.mcp_manager._servers)} servers")

    def _register_delegate_tool(self, tools):
        """Register delegate tool with LLM and read-only child tools injected."""
        from jay_agent_core.tools.base import ToolResult as _TR
        from jay_agent_core.tools.handlers_delegate import HANDLERS as _DH

        handler = _DH.get("delegate")
        if not handler:
            return

        # Build read-only tool specs for child agent
        readonly_names = {"read_file", "list_files", "grep_files", "find_files", "search_files"}
        child_tools = []
        for t in tools:
            if t.name in readonly_names:
                def _make(tool_obj):
                    async def _h(args, user_id=None, meta=None, cancel=None):
                        try:
                            result = await tool_obj.aexecute(**args)
                            return _TR(ok=True, data=result)
                        except Exception as e:
                            return _TR(ok=False, error=str(e))
                    return _h
                child_tools.append({
                    "name": t.name,
                    "handler": _make(t),
                    "schema": t.to_openai_schema(),
                    "is_core": True,
                    "timeout": 30.0,
                })

        llm_ref = self.llm
        workspace_ref = str(self.workspace)

        async def _delegate_handler(args, user_id=None, meta=None, cancel=None):
            meta = {**(meta or {}), "llm": llm_ref, "workspace": workspace_ref, "child_tools": child_tools}
            return await handler(args, user_id or "", meta, cancel)

        # Find delegate schema from TOOL_SCHEMAS
        from jay_agent_core.tools.schemas import TOOL_SCHEMAS
        delegate_schema = next((s for s in TOOL_SCHEMAS if s["function"]["name"] == "delegate"), None)
        if delegate_schema:
            self.agent.registry_enhanced.register(
                name="delegate",
                handler=_delegate_handler,
                schema=delegate_schema,
                is_core=True,
                timeout=120.0,
            )

    def _get_system_prompt(self) -> str:
        """Get system prompt for coding agent using structured context blocks."""
        from datetime import datetime

        from jay_agent_core.context import split_agents_md
        from jay_agent_core.context_blocks import ContextAssembler, ContextBlock

        model = self.llm.config.model
        provider = getattr(self.llm.config, "provider", None)
        context_window = get_context_window(model, provider)
        system_budget = int(context_window * 0.20)

        assembler = ContextAssembler(total_budget=system_budget, model=model)

        # P1: Identity — who the agent is and where it works
        identity = (
            f"You are an expert coding assistant with access to file operations, "
            f"code generation, shell commands, and web tools.\n"
            f"Workspace: {self.workspace}"
        )
        assembler.add_block(ContextBlock(type="identity", content=identity, priority=1, compressible=False))

        # P1: Constraints — hard rules (from AGENTS.md Always Loaded or defaults)
        default_constraints = (
            "- Be helpful, precise, and always confirm destructive operations\n"
            "- When generating code, provide clean, well-documented, production-ready code\n"
            "- For weather queries, use run_command(\"curl -s wttr.in/<city>?format=3\")\n"
            "- For other real-time information, use search_web\n"
            "- Use `delegate` for tasks requiring broad exploration (searching 3+ files, "
            "pattern finding across codebase, analyzing unfamiliar code areas). "
            "Do NOT delegate when you already know the exact file/location or need to write files.\n"
            "- Use `scratchpad` to record key findings, decisions, and next steps during "
            "multi-step tasks. This ensures continuity if context resets."
        )
        agents_md = self.context_manager.load_agents_md()
        if agents_md:
            constraints, knowledge = split_agents_md(agents_md)
            if constraints:
                assembler.add_block(ContextBlock(type="constraints", content=constraints, priority=1, compressible=False))
            else:
                assembler.add_block(ContextBlock(type="constraints", content=default_constraints, priority=1, compressible=False))
            if knowledge:
                assembler.add_block(ContextBlock(type="project-context", content=knowledge, priority=3, source="AGENTS.md"))
        else:
            assembler.add_block(ContextBlock(type="constraints", content=default_constraints, priority=1, compressible=False))

        # Check for SYSTEM.md override — if present, inject as high-priority block
        system_md = self.context_manager.load_system_md()
        if system_md:
            assembler.add_block(ContextBlock(type="project-context", content=system_md, priority=2, source="SYSTEM.md", compressible=False))

        # P4: Skills
        if self.skill_manager and len(self.skill_manager) > 0:
            skills_prompt = self.skill_manager.get_all_skills_prompt()
            assembler.add_block(ContextBlock(type="skills", content=skills_prompt, priority=4))

        # P2: Active tools
        if hasattr(self, 'agent') and hasattr(self.agent, 'registry_enhanced'):
            schemas = self.agent.registry_enhanced.get_schemas() if len(self.agent.registry_enhanced) > 0 else []
            names = [s.get("function", {}).get("name", "") for s in schemas if isinstance(s, dict)]
            if names:
                assembler.add_block(ContextBlock(
                    type="active-tools",
                    content="Currently activated: " + ", ".join(names),
                    priority=2, compressible=False,
                ))

        # P3: Runtime context
        runtime = f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        assembler.add_block(ContextBlock(type="runtime", content=runtime, priority=3, compressible=False))

        # P2: Scratchpad — persistent notes from previous sessions
        scratchpad_path = self.workspace / ".jayclaw" / "scratchpad.md"
        if scratchpad_path.exists():
            scratchpad_content = scratchpad_path.read_text(encoding="utf-8").strip()
            if scratchpad_content:
                assembler.add_block(ContextBlock(
                    type="scratchpad", content=scratchpad_content,
                    priority=2, compressible=False, source=".jayclaw/scratchpad.md",
                ))

        # P5: Appendix (APPEND_SYSTEM.md)
        append_md = self.context_manager.load_append_system_md()
        if append_md:
            assembler.add_block(ContextBlock(type="appendix", content=append_md, priority=5, source="APPEND_SYSTEM.md"))

        return assembler.assemble()

    # Base slash commands for tab completion
    BASE_COMMANDS = [
        "/help",
        "/exit",
        "/quit",
        "/clear",
        "/files",
        "/status",
        "/tree",
        "/fork",
        "/compact",
        "/session",
        "/sessions",
        "/skills",
        "/extensions",
        "/prompts",
        "/reload",
        "/config",
        "/queue",
        "/export",
        "/share",
        "/model",
        "/login",
        "/logout",
        "/resilience",
        "/cost",
        "/usage",
        "/agents-init",
        "/agents-summarize",
    ]

    def _build_commands(self) -> list[str]:
        """Build full command list including dynamic /skill: entries."""
        commands = list(self.BASE_COMMANDS)
        if self.skill_manager:
            for skill in self.skill_manager.list_skills():
                commands.append(f"/skill:{skill.name}")
        if self.prompt_manager:
            for name in self.prompt_manager.list_templates():
                commands.append(f"/{name}")
        return commands

    def clear_history(self) -> None:
        """Clear conversation history on the inner agent and reset session."""
        try:
            self.context_manager.invalidate_token_cache()
        except AttributeError:
            pass
        if hasattr(self.agent, "clear_history"):
            self.agent.clear_history()
        from jay_agent_core.session import Session
        self.session = Session(workspace=str(self.workspace))

    def change_workspace(self, new_workspace: str) -> str:
        """Change the working directory and reinitialize file/shell tools.

        Args:
            new_workspace: New workspace path (absolute or relative)

        Returns:
            Resolved absolute path of the new workspace

        Raises:
            ValueError: If path does not exist
        """
        try:
            self.context_manager.invalidate_token_cache()
        except AttributeError:
            pass
        new_path = Path(new_workspace).resolve()
        if not new_path.exists():
            raise ValueError(f"Path does not exist: {new_path}")
        if not new_path.is_dir():
            raise ValueError(f"Path is not a directory: {new_path}")

        self.workspace = new_path

        # Reinitialize tools with new workspace
        from .tools import CodeTools, FileTools, ShellTools
        file_tools = FileTools(str(self.workspace))
        code_tools = CodeTools()
        shell_tools = ShellTools()

        new_tools = []
        for tool_instance in [file_tools, code_tools, shell_tools]:
            for attr_name in dir(tool_instance):
                attr = getattr(tool_instance, attr_name)
                if isinstance(attr, Tool):
                    new_tools.append(attr)

        # Re-register in registry_enhanced (overwrite existing entries)
        def make_handler(t):
            async def _handler(args, user_id=None, meta=None, cancel=None):
                from jay_agent_core.tools.base import ToolResult
                try:
                    result = await t.aexecute(**args)
                    return ToolResult(ok=True, data=result)
                except Exception as e:
                    return ToolResult(ok=False, error=str(e))
            return _handler

        for tool_obj in new_tools:
            self.agent.registry_enhanced.register(
                name=tool_obj.name,
                handler=make_handler(tool_obj),
                schema=tool_obj.to_openai_schema(),
                is_core=True,
                timeout=60.0,
            )

        # Update system prompt with new workspace path
        new_prompt = self._get_system_prompt()
        self.agent.system_prompt = new_prompt
        if self.agent.history and self.agent.history[0].role == "system":
            from jay_llm import Message
            self.agent.history[0] = Message(role="system", content=new_prompt)

        # Rebuild cost tracker so usage data is written to the new workspace
        if self.cost_tracker is not None:
            try:
                self.cost_tracker = CostTracker(self.workspace)
                self.agent.billing_hook = self.cost_tracker
            except Exception:
                # Cost tracking is best-effort — never block a workspace switch on it
                pass

        # Move file reference parser onto the new workspace
        try:
            self.file_ref_parser = FileReferenceParser(self.workspace)
        except Exception:
            logger.exception("file_ref_parser rebind failed after workspace switch")

        return str(self.workspace)

    def run_interactive(self) -> None:
        """Run interactive chat session."""
        self.ui.system(f"Workspace: {self.workspace}")
        self.ui.separator()

        # Offer to initialize per-workspace AGENTS.md if missing
        self._maybe_init_agents_md()

        # Set up interactive prompt with completion and history
        history_file = str(self.workspace / ".sessions" / ".input_history")
        prompt = InteractivePrompt(
            commands=self._build_commands(),
            workspace=str(self.workspace),
            history_file=history_file,
        )

        try:
            while True:
                # Show queue status if messages queued
                if self.agent.message_queue:
                    queue_status = self.agent.message_queue.get_status()
                    if "Queued" in queue_status:
                        self.ui.system(f"📬 {queue_status}")

                # Get user input with tab completion
                try:
                    user_input = prompt.ask("You> ")
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                # Check for queue commands
                if user_input.startswith("!"):
                    # !message = steering (interrupt)
                    steering_msg = user_input.lstrip("!")
                    self.agent.message_queue.add_steering(steering_msg)
                    self.ui.system(f"⚡ Queued steering message: {steering_msg[:50]}...")
                    continue

                if user_input.startswith(">>"):
                    # >>message = follow-up (wait until done)
                    followup_msg = user_input.lstrip(">").strip()
                    self.agent.message_queue.add_followup(followup_msg)
                    self.ui.system(f"📝 Queued follow-up message: {followup_msg[:50]}...")
                    continue

                # Check for file references
                if "@" in user_input:
                    preview = self.file_ref_parser.get_reference_preview(user_input)
                    if preview:
                        self.ui.system(preview)

                        # Expand references
                        expanded_input = self.file_ref_parser.expand_references(user_input)

                        # Show expansion if significant
                        if len(expanded_input) > len(user_input) + 100:
                            added = len(expanded_input) - len(user_input)
                            self.ui.system(f"→ Added {added} chars from files")

                        # Use expanded input
                        user_input = expanded_input

                # Display user message
                self.ui.user(user_input[:200] + "..." if len(user_input) > 200 else user_input)

                # Get agent response using arun() for dynamic tool support
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(asyncio.run, self.agent.arun(user_input))
                            response = future.result()
                    else:
                        response = loop.run_until_complete(self.agent.arun(user_input))
                except RuntimeError:
                    response = asyncio.run(self.agent.arun(user_input))

                # Display response
                self.ui.assistant(response.content)

                # Add to session
                if self.session:
                    self.session.add_message("user", user_input)
                    self.session.add_message("assistant", response.content)

        except KeyboardInterrupt:
            pass
        finally:
            # Clean up queued messages
            if self.agent.message_queue:
                cleared = self.agent.message_queue.clear()
                if cleared:
                    self.ui.system(f"\nCleared {len(cleared)} queued messages")
            # Offer to summarize this session into AGENTS.md
            self._maybe_summarize_to_agents_md()
            self.ui.system("\nGoodbye!")

    def _handle_command(self, command: str) -> None:
        """Handle slash commands.

        Args:
            command: Command string
        """
        cmd = command.lower().strip()

        if cmd == "/exit" or cmd == "/quit":
            raise KeyboardInterrupt()

        elif cmd == "/clear":
            self.agent.clear_history()
            self.ui.clear()
            self.ui.system("Conversation cleared")

        elif cmd == "/help":
            self.ui.panel(
                """
**Available Commands:**

/help       - Show this help
/exit       - Exit the agent
/clear      - Clear conversation
/files      - List files in workspace
/status     - Show agent status

**Tools Available:**
- read_file, write_file, list_files
- generate_code, explain_code
- run_command, git_status, git_diff
            """,
                title="Help",
            )

        elif cmd == "/files":
            files = FileTools(str(self.workspace)).list_files()
            self.ui.panel(files, title="Files")

        elif cmd == "/status":
            self.ui.panel(
                f"""
**Agent Status**

Model: {self.agent.llm.config.model}
Workspace: {self.workspace}
Messages: {len(self.agent.history)}
Tools: {len(self.agent.registry)}
            """,
                title="Status",
            )

        elif cmd.startswith("/tree"):
            self._show_tree()

        elif cmd.startswith("/fork"):
            parts = cmd.split(maxsplit=1)
            fork_name = parts[1] if len(parts) > 1 else None
            self._fork_session(fork_name)

        elif cmd.startswith("/compact"):
            parts = cmd.split(maxsplit=1)
            instructions = parts[1] if len(parts) > 1 else None
            self._compact_session(instructions)

        elif cmd.startswith("/session"):
            self._show_session_info()

        elif cmd.startswith("/sessions"):
            self._list_sessions()

        elif cmd.startswith("/skill:"):
            skill_name = cmd.split(":", 1)[1]
            self._invoke_skill(skill_name)

        elif cmd.startswith("/skills"):
            self._list_skills()

        elif cmd.startswith("/extensions"):
            self._list_extensions()

        elif cmd.startswith("/prompts"):
            self._list_prompts()

        elif cmd.startswith("/reload"):
            self._reload_resources()

        elif cmd.startswith("/config"):
            self._show_config()

        elif cmd.startswith("/queue"):
            self._show_queue()

        elif cmd.startswith("/export"):
            parts = cmd.split(maxsplit=1)
            filename = parts[1] if len(parts) > 1 else None
            self._export_session(filename)

        elif cmd.startswith("/share"):
            self._share_session()

        elif cmd.startswith("/model"):
            parts = cmd.split(maxsplit=1)
            new_model = parts[1] if len(parts) > 1 else None
            self._switch_model(new_model)

        elif cmd.startswith("/login"):
            self._login()

        elif cmd.startswith("/logout"):
            parts = cmd.split(maxsplit=1)
            provider = parts[1] if len(parts) > 1 else None
            self._logout(provider)

        elif cmd.startswith("/resilience"):
            self._show_resilience_status()

        elif cmd.startswith("/cost") or cmd.startswith("/usage"):
            self._show_cost_summary()

        elif cmd.startswith("/context"):
            self._show_context_status()

        elif cmd.startswith("/handoff"):
            parts = cmd.split(maxsplit=1)
            extra_goal = parts[1] if len(parts) > 1 else ""
            self._generate_handoff(extra_goal)

        elif cmd.startswith("/agents-init"):
            self._init_agents_md_now(force=True)

        elif cmd.startswith("/agents-summarize"):
            self._summarize_to_agents_md_now()

        elif cmd.startswith("/"):
            # Check if it's a prompt template
            template_name = cmd.lstrip("/").split()[0]
            if self.prompt_manager and template_name in self.prompt_manager:
                # Extract variables from rest of command
                args_str = cmd.split(maxsplit=1)[1] if " " in cmd else ""
                self._expand_prompt(template_name, args_str)
                return

            # Try extension commands
            if self.extension_manager:
                ext_cmd = cmd.lstrip("/").split()[0]
                cmd_args = cmd.split(maxsplit=1)[1] if " " in cmd else None
                try:
                    result = self.extension_manager.handle_command(ext_cmd, cmd_args)
                    self.ui.panel(str(result), title=f"/{ext_cmd}")
                    return
                except (ValueError, KeyError):
                    pass

            self.ui.error(f"Unknown command: {command}")

    def _show_tree(self):
        """Show session tree."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        tree_text = "**Session Tree**\n\n"
        path = self.session.get_current_conversation()

        for i, entry in enumerate(path):
            indent = "  " * min(i, 5)
            preview = entry.content[:60].replace("\n", " ")
            tree_text += f"{indent}• [{entry.role}] {preview}...\n"

        tree_text += f"\nTotal entries: {len(self.session.tree.entries)}"
        tree_text += f"\nCurrent path: {len(path)}"
        self.ui.panel(tree_text, title="Session Tree")

    def _fork_session(self, fork_name: str | None):
        """Fork current session."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        conversation = self.session.get_current_conversation()
        if not conversation:
            self.ui.error("No messages to fork")
            return

        # Fork from last message
        name = fork_name or f"{self.session.name}-fork"
        fork = self.session.fork(conversation[-1].id, name)

        save_path = fork.save()
        self.ui.system(f"✓ Forked session: {name}")
        self.ui.system(f"  Copied {len(fork.tree.entries)} entries")
        self.ui.system(f"  Saved to: {save_path}")

    def _compact_session(self, instructions: str | None):
        """Compact session messages using context compression.

        Translates ``jay_llm.Message`` objects to the dict shape expected by
        ``compress_messages`` before passing them in, then maps the result back
        onto the agent's history.
        """
        try:
            self.context_manager.invalidate_token_cache()
        except AttributeError:
            pass
        messages = self.agent.history
        if not messages:
            self.ui.error("No messages to compact")
            return

        before = len(messages)

        # Force compression by setting ratio to 1.0 (triggers Level 2)
        model = self.llm.config.model
        provider = getattr(self.llm.config, "provider", None)
        max_tokens = get_context_window(model, provider)

        # Convert Message → dict so compress_messages can call .get(...)
        msg_dicts = []
        for m in messages:
            entry = {"role": m.role, "content": m.content or ""}
            meta = getattr(m, "metadata", None) or {}
            if "tool_calls" in meta:
                entry["tool_calls"] = meta["tool_calls"]
            if "name" in meta:
                entry["name"] = meta["name"]
            msg_dicts.append(entry)

        compressed_dicts = compress_messages(
            msg_dicts, max_tokens, max_tokens, CompressionConfig()
        )

        from jay_llm import Message as LLMMessage
        new_history = []
        for d in compressed_dicts:
            meta: dict = {}
            if "tool_calls" in d:
                meta["tool_calls"] = d["tool_calls"]
            if "name" in d:
                meta["name"] = d["name"]
            new_history.append(LLMMessage(
                role=d["role"],
                content=d.get("content") or "",
                metadata=meta or None,
            ))
        self.agent.history = new_history

        self.ui.system(f"✓ Compacted: {before} messages → {len(new_history)} messages")

    def _list_sessions(self):
        """List available sessions."""
        session_mgr = SessionManager(self.workspace)
        sessions = session_mgr.list_sessions(limit=20)

        if not sessions:
            self.ui.system("No sessions found")
            self.ui.system(f"Sessions are saved to: {self.workspace}/.sessions/")
            return

        sessions_text = session_mgr.format_session_list(sessions)

        if len(sessions) == 20:
            sessions_text += "\n\n... (showing most recent 20)"

        self.ui.panel(sessions_text, title=f"Available Sessions ({len(sessions)})")
        self.ui.system("Use `jay-code --resume` to select a session")

    def _show_session_info(self):
        """Show session information."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        info = self.session.get_info()
        info_text = f"""
**Session Information**

ID: {info["id"][:8]}...
Name: {info["name"]}
Created: {info["created_at"][:19]}
Updated: {info["updated_at"][:19]}

Entries: {info["entries"]}
Current path: {info["current_path_length"]}
Branches: {info["branches"]}

Tokens: {info["metadata"].get("tokens_used", 0)}
Cost: ${info["metadata"].get("cost", 0.0):.4f}
        """
        self.ui.panel(info_text, title="Session")

    def _invoke_skill(self, skill_name: str):
        """Invoke a skill."""
        if not self.skill_manager:
            self.ui.error("Skills not enabled")
            return

        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            self.ui.error(f"Skill '{skill_name}' not found")
            self.ui.system("Use /skills to see available skills")
            return

        # Show skill
        skill_prompt = skill.to_prompt()
        self.ui.panel(skill_prompt, title=f"Skill: {skill_name}")
        self.ui.system("Skill context loaded. Ask your question now.")

    def _list_skills(self):
        """List available skills."""
        if not self.skill_manager:
            self.ui.error("Skills not enabled")
            return

        if len(self.skill_manager) == 0:
            self.ui.system("No skills found")
            self.ui.system("Create skills in .jayclaw/skills/skill-name/SKILL.md")
            return

        skills_text = "**Available Skills**\n\n"
        for skill in self.skill_manager.list_skills():
            skills_text += f"• **{skill.name}**\n"
            skills_text += f"  {skill.description}\n\n"

        skills_text += "Use `/skill:name` to invoke a skill."
        self.ui.panel(skills_text, title=f"Skills ({len(self.skill_manager)})")

    def _list_extensions(self):
        """List loaded extensions."""
        if not self.extension_manager:
            self.ui.error("Extensions not enabled")
            return

        if len(self.extension_manager.extensions) == 0:
            self.ui.system("No extensions loaded")
            self.ui.system("Place extensions in .jayclaw/extensions/")
            return

        ext_text = "**Loaded Extensions**\n\n"
        for name in self.extension_manager.extensions.keys():
            ext_text += f"• {name}\n"

        # List custom commands
        commands = self.extension_manager.api.get_commands()
        if commands:
            ext_text += "\n**Custom Commands**:\n"
            for cmd in commands.keys():
                ext_text += f"• /{cmd}\n"

        # List registered tools count
        ext_text += f"\n**Tools**: {len(self.agent.registry)} total"

        self.ui.panel(ext_text, title=f"Extensions ({len(self.extension_manager.extensions)})")

    def _show_help(self):
        """Show comprehensive help."""
        help_text = """
**Built-in Commands:**

/help       - Show this help
/exit       - Exit agent
/clear      - Clear conversation
/status     - Agent status
/config     - Show configuration
/queue      - Show message queue
/files      - List workspace files

**Session Management:**

/session    - Show current session info
/sessions   - List all available sessions
/tree       - Show conversation tree
/fork [name] - Fork session from current point
/compact [instructions] - Compact old messages
/export [file] - Export session to HTML
/share      - Share session via GitHub Gist
/reload     - Reload extensions, skills, prompts, context

**Skills & Extensions:**

/skills     - List available skills
/skill:name - Invoke a skill
/extensions - List loaded extensions
/prompts    - List prompt templates
/template   - Expand a template

**Model & Auth:**

/model [provider/model] - Switch LLM model
/login      - OAuth login (subscription accounts)
/logout <provider> - Logout from provider

**Context Files:**

• AGENTS.md - Project instructions (auto-loaded)
• SYSTEM.md - Override system prompt
• APPEND_SYSTEM.md - Append to system prompt

**Message Queue:**

While agent is working, you can queue messages:
  !message     - Steering (interrupt after current tool)
  >>message    - Follow-up (wait until agent finishes)

Use /queue to see queued messages.

**File References:**

Use @filename to auto-include file contents:
  @src/main.py - Include main.py in your message
  @README.md - Include README
  @test.py and @utils.py - Multiple files

Files are automatically read and added to context!

**Features:**

• Sessions auto-save to .sessions/
• Extensions auto-load from .jayclaw/extensions/
• Skills auto-discover from .jayclaw/skills/
• Prompts auto-load from .jayclaw/prompts/
• Context auto-load from AGENTS.md, SYSTEM.md
• Use /tree to navigate conversation history
• Use /fork to create alternate branches
• Queue messages with ! or >>
        """
        self.ui.panel(help_text, title="Help")

    def _list_prompts(self):
        """List available prompt templates."""
        if not self.prompt_manager or len(self.prompt_manager) == 0:
            self.ui.system("No prompts found")
            self.ui.system("Create prompts in .jayclaw/prompts/*.md")
            return

        prompts_text = "**Available Prompt Templates**\n\n"
        for template in self.prompt_manager.list_templates():
            prompts_text += f"• **/{template.name}**\n"
            if template.variables:
                prompts_text += f"  Variables: {', '.join(template.variables)}\n"
            # Show first line as description
            first_line = template.content.split("\n")[0].strip("# ").strip()
            prompts_text += f"  {first_line}\n\n"

        prompts_text += "Use `/template_name` to expand a template."
        self.ui.panel(prompts_text, title=f"Prompts ({len(self.prompt_manager)})")

    def _expand_prompt(self, template_name: str, args: str):
        """Expand a prompt template.

        Args:
            template_name: Template name
            args: Arguments string (key=value format)
        """
        template = self.prompt_manager.get_template(template_name)
        if not template:
            self.ui.error(f"Template '{template_name}' not found")
            return

        # Parse arguments (simple key=value parsing)
        kwargs = {}
        if args:
            # Support both space and comma separated
            parts = args.replace(",", " ").split()
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    # Remove quotes if present
                    value = value.strip("\"'")
                    kwargs[key] = value

        # Show template info if no args and has variables
        if template.variables and not kwargs:
            vars_text = "**Template Variables**:\n\n"
            for var in template.variables:
                vars_text += f"• {var}\n"
            usage_args = " ".join(f"{v}=value" for v in template.variables)
            vars_text += f"\n**Usage**: `/{template_name} {usage_args}`"
            vars_text += f'\n\n**Example**: `/{template_name} {template.variables[0]}="example"`'
            self.ui.panel(vars_text, title=f"Template: {template_name}")
            return

        # Render template
        rendered = template.render(**kwargs)

        # Display nicely
        self.ui.panel(rendered, title=f"Expanded: /{template_name}")

        # Automatically send to agent
        self.ui.system("Sending prompt to agent...")

        # Add to session
        if self.session:
            self.session.add_message("user", rendered)

        # Get response using arun()
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.agent.arun(rendered))
                    response = future.result()
            else:
                response = loop.run_until_complete(self.agent.arun(rendered))
        except RuntimeError:
            response = asyncio.run(self.agent.arun(rendered))

        # Display response
        self.ui.assistant(response.content)

    def _export_session(self, filename: str | None):
        """Export session to HTML."""
        if not self.session:
            self.ui.error("No session to export")
            return

        from pathlib import Path

        from jay_agent_core import SessionExporter

        # Determine output path
        if filename:
            output_path = Path(filename)
        else:
            # Auto-generate
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"{self.session.name}_{timestamp}.html")

        try:
            exported = SessionExporter.export_to_html(
                self.session, output_path, title=self.session.name
            )
            self.ui.system(f"✓ Exported to: {exported}")
            self.ui.system(f"  Open in browser: file://{exported.absolute()}")
        except Exception as e:
            self.ui.error(f"Export failed: {e}")

    def _switch_model(self, model_name: str | None):
        """Switch LLM model.

        Args:
            model_name: New model name (format: provider/model)
        """
        if not model_name:
            # Show current model
            current = f"{self.agent.llm.config.provider}/{self.agent.llm.config.model}"
            self.ui.panel(
                f"""
**Current Model**

Provider: {self.agent.llm.config.provider}
Model: {self.agent.llm.config.model}
Full: {current}

**Switch Model**:
  /model openai/gpt-4
  /model anthropic/claude-3-sonnet
  /model groq/llama-3.1-70b

**Available Providers**:
  openai, anthropic, google, azure, groq,
  mistral, openrouter, bedrock, xai, cerebras,
  cohere, perplexity, deepseek, together
            """,
                title="Model",
            )
            return

        # Parse provider/model
        if "/" in model_name:
            provider, model = model_name.split("/", 1)
        else:
            # Assume same provider
            provider = self.agent.llm.config.provider
            model = model_name

        try:
            # Create new LLM
            from jay_llm import LLM

            new_llm = LLM(provider=provider, model=model)

            # Update agent
            self.agent.llm = new_llm
            self.llm = new_llm

            self.ui.system(f"✓ Switched to {provider}/{model}")

        except Exception as e:
            self.ui.error(f"Failed to switch model: {e}")

    def _login(self):
        """Login to a provider via OAuth."""

        # Supported providers (examples)

        self.ui.panel(
            """
**OAuth Login**

Currently, OAuth login is a framework feature.
Most providers support API keys directly.

For subscription login (Claude Pro, ChatGPT Plus):
- Set up OAuth app in provider console
- Configure client_id/secret in ~/.jayclaw/oauth_providers.json
- Then use /login

For now, use API keys:
  export OPENAI_API_KEY=sk-...
  export ANTHROPIC_API_KEY=sk-ant-...
            """,
            title="OAuth Login",
        )

    def _logout(self, provider: str | None):
        """Logout from a provider.

        Args:
            provider: Provider name
        """
        from jay_agent_core import AuthManager

        if not provider:
            self.ui.error("Usage: /logout <provider>")
            self.ui.system("Example: /logout anthropic")
            return

        auth_mgr = AuthManager()

        if auth_mgr.logout(provider):
            self.ui.system(f"✓ Logged out from {provider}")
        else:
            self.ui.system(f"Not logged in to {provider}")

    def _share_session(self):
        """Share session via GitHub Gist."""
        if not self.session:
            self.ui.error("No session to share")
            return

        import os

        from jay_agent_core import GistSharer

        # Get GitHub token
        github_token = os.getenv("GITHUB_TOKEN")

        if not github_token:
            self.ui.error("GITHUB_TOKEN not set")
            self.ui.system("Get token from: https://github.com/settings/tokens")
            self.ui.system("Set: export GITHUB_TOKEN=your_token")
            return

        try:
            sharer = GistSharer(github_token)

            self.ui.system("Uploading to GitHub Gist...")

            info = sharer.share_session(
                self.session, public=False, description=f"JayClaw: {self.session.name}"
            )

            self.ui.system("✓ Shared as private gist!")
            self.ui.panel(
                f"""
**Gist Created**

URL: {info["url"]}
ID: {info["id"]}
Public: {info["public"]}

Share this URL to give others access.
            """,
                title="Shared",
            )

        except Exception as e:
            self.ui.error(f"Share failed: {e}")

    def _show_queue(self):
        """Show message queue status."""
        queue = self.agent.message_queue

        if not queue:
            self.ui.system("Message queue is empty")
            self.ui.system("\nQueue messages while agent is working:")
            self.ui.system("  !message    - Steering (interrupt after current tool)")
            self.ui.system("  >>message   - Follow-up (wait until done)")
            return

        queue_text = f"**Message Queue** ({len(queue)} messages)\n\n"

        steering = [m for m in queue.queue if m.type.value == "steering"]
        followup = [m for m in queue.queue if m.type.value == "followup"]

        if steering:
            queue_text += "**Steering Messages** (interrupt):\n"
            for i, msg in enumerate(steering, 1):
                preview = msg.content[:60]
                queue_text += f"{i}. {preview}...\n"
            queue_text += "\n"

        if followup:
            queue_text += "**Follow-up Messages** (after completion):\n"
            for i, msg in enumerate(followup, 1):
                preview = msg.content[:60]
                queue_text += f"{i}. {preview}...\n"

        queue_text += "\n**Modes**:\n"
        queue_text += f"• Steering: {queue.steering_mode}\n"
        queue_text += f"• Follow-up: {queue.followup_mode}"

        self.ui.panel(queue_text, title="Queue")

    def _show_config(self):
        """Show current configuration."""
        from .config import ConfigManager

        config_mgr = ConfigManager(self.workspace)
        config = config_mgr.load_config()

        config_text = f"""
**Agent Configuration**

Provider: {config.provider}
Model: {config.model or "default"}
Temperature: {config.temperature}

**Features**

Extensions: {"enabled" if config.enable_extensions else "disabled"}
Skills: {"enabled" if config.enable_skills else "disabled"}
Prompts: {"enabled" if config.enable_prompts else "disabled"}
Context: {"enabled" if config.enable_context else "disabled"}

**Session**

Auto-save: {"yes" if config.auto_save_session else "no"}
Cleanup: {config.session_cleanup_days} days

**Display**

Verbose: {config.verbose}
Theme: {config.theme}

**Config Files**

Global: ~/.jayclaw/config.json
Project: .jayclaw/config.json
        """

        self.ui.panel(config_text, title="Configuration")
        self.ui.system("Edit config files or use environment variables")

    def _reload_resources(self):
        """Reload extensions, skills, prompts, and context."""
        reloaded = []

        # Reload extensions
        if self.extension_manager:
            # Clear and reload
            old_count = len(self.extension_manager.extensions)
            self.extension_manager.extensions.clear()
            self._load_extensions()
            new_count = len(self.extension_manager.extensions)
            reloaded.append(f"Extensions: {new_count} (was {old_count})")

        # Reload skills
        if self.skill_manager:
            old_count = len(self.skill_manager)
            self.skill_manager.skills.clear()
            self.skill_manager.discover_skills([])
            new_count = len(self.skill_manager)
            reloaded.append(f"Skills: {new_count} (was {old_count})")

        # Reload prompts
        if self.prompt_manager:
            old_count = len(self.prompt_manager)
            self.prompt_manager.templates.clear()
            self.prompt_manager.discover_prompts([])
            new_count = len(self.prompt_manager)
            reloaded.append(f"Prompts: {new_count} (was {old_count})")

        # Reload system prompt (context files)
        new_prompt = self._get_system_prompt()
        # Update agent's system prompt
        if self.agent.history and self.agent.history[0].role == "system":
            self.agent.history[0].content = new_prompt
            reloaded.append("Context: Reloaded")

        if reloaded:
            self.ui.system("✓ Reloaded resources:")
            for item in reloaded:
                self.ui.system(f"  • {item}")
        else:
            self.ui.system("No resources to reload")

    def _show_status(self):
        """Show comprehensive status."""
        status_text = f"""
**Agent Configuration**

Model: {self.agent.llm.config.model}
Provider: {self.agent.llm.config.provider}
Workspace: {self.workspace}

**Current State**

Messages in history: {len(self.agent.history)}
Tools available: {len(self.agent.registry)}
"""

        if self.session:
            info = self.session.get_info()
            status_text += f"""
**Session**

Name: {self.session.name}
Entries: {info["entries"]}
Current path: {info["current_path_length"]}
Branches: {info["branches"]}
"""

        if self.skill_manager:
            status_text += f"\n**Skills**: {len(self.skill_manager)} loaded"

        if self.extension_manager:
            ext_count = len(self.extension_manager.extensions)
            cmd_count = len(self.extension_manager.api.get_commands())
            status_text += f"\n**Extensions**: {ext_count} loaded, {cmd_count} commands"

        if self.prompt_manager:
            status_text += f"\n**Prompts**: {len(self.prompt_manager)} loaded"

        # Show context files
        agents_md = self.context_manager.find_context_files("AGENTS.md")
        if agents_md:
            status_text += f"\n**Context**: {len(agents_md)} AGENTS.md files"

        self.ui.panel(status_text, title="Status")

    def run_once(self, message: str) -> str:
        """Run agent with a single message (sync wrapper).

        Args:
            message: User message

        Returns:
            Agent response
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, create task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.agent.arun(message))
                    return future.result().content
            else:
                return loop.run_until_complete(self.agent.arun(message)).content
        except RuntimeError:
            return asyncio.run(self.agent.arun(message)).content

    async def arun_once(self, message: str) -> str:
        """Run agent with a single message (async).

        Args:
            message: User message

        Returns:
            Agent response
        """
        response = await self.agent.arun(message)
        return response.content

    def _show_resilience_status(self):
        """Show resilience system status."""
        if not self.profile_manager:
            self.ui.system("Resilience not enabled")
            self.ui.system("\nTo enable resilience:")
            self.ui.system("  1. Set multiple API keys:")
            self.ui.system("     export OPENAI_API_KEY=sk-...")
            self.ui.system("     export OPENAI_API_KEY_2=sk-...")
            self.ui.system("     export ANTHROPIC_API_KEY=sk-ant-...")
            self.ui.system("  2. Restart agent")
            return

        status = get_profile_status(self.profile_manager)

        status_text = f"""
**Resilience Status**

Total API keys: {status["total_profiles"]}
Available: {status["available_profiles"]}
In cooldown: {status["cooldown_profiles"]}

**Profiles:**
"""

        for i, profile in enumerate(status["profiles"], 1):
            provider = profile["provider"]
            key_idx = profile["key_index"]
            available = "✓" if profile["available"] else "✗ (cooldown)"

            status_text += f"\n{i}. {provider} (key #{key_idx}): {available}"

        status_text += "\n\n**Features:**\n"
        status_text += "• Automatic API key rotation on rate limits\n"
        status_text += "• Per-failure-type cooldowns\n"
        status_text += "• Model fallback on context overflow\n"

        self.ui.panel(status_text, title="Resilience")

    def _show_cost_summary(self):
        """Show cost tracking summary."""
        if not self.cost_tracker:
            self.ui.system("Cost tracking not enabled")
            return

        summary_text = self.cost_tracker.format_summary()
        self.ui.panel(summary_text, title="Cost Tracking")

        # Show usage file location
        self.ui.system(f"\nUsage data: {self.cost_tracker.usage_file}")

    def _show_context_status(self) -> None:
        from jay_agent_core.context import compute_utilization

        history = getattr(self.agent, "history", []) or []
        cfg = getattr(self.llm, "config", None)
        model = getattr(cfg, "model", None)
        provider = getattr(cfg, "provider", None)
        max_tokens = detect_context_window(model, provider)
        messages = [
            {
                "role": m.role,
                "content": m.content,
                "metadata": getattr(m, "metadata", None) or {},
            }
            for m in history
        ]
        util = compute_utilization(messages, max_tokens=max_tokens, model=model)
        self.ui.panel(
            f"Tokens: {util.current_tokens}/{util.max_tokens} ({util.percent}%)\n"
            f"Zone: {util.zone}",
            title="Context",
        )

    def _generate_handoff(self, extra_goal: str = "") -> None:
        from .handoff import (
            extract_handoff_data_from_history,
            generate_handoff,
        )
        from jay_agent_core.context import compute_utilization

        progress_path = self.workspace / ".jayclaw" / "progress.json"
        history = getattr(self.agent, "history", []) or []
        messages = [
            {
                "role": m.role,
                "content": m.content,
                "metadata": getattr(m, "metadata", None) or {},
            }
            for m in history
        ]
        data = extract_handoff_data_from_history(messages, progress_path)
        if extra_goal:
            data.goal = extra_goal
        cfg = getattr(self.llm, "config", None)
        model = getattr(cfg, "model", None)
        provider = getattr(cfg, "provider", None)
        max_tokens = detect_context_window(model, provider)
        util = compute_utilization(messages, max_tokens=max_tokens, model=model)
        path = generate_handoff(data, self.workspace, ratio=util.ratio)
        self.ui.system(f"Handoff written: {path}")

    # ------------------------------------------------------------------
    # Per-workspace AGENTS.md (init at session start, summarize at end)
    # ------------------------------------------------------------------

    @staticmethod
    def _no_init_marker(workspace: Path) -> Path:
        return workspace / ".jayclaw" / ".no-agents-md"

    @staticmethod
    def _no_summary_marker(workspace: Path) -> Path:
        return workspace / ".jayclaw" / ".no-summary"

    def _maybe_init_agents_md(self) -> None:
        """At session start: if no AGENTS.md anywhere up the tree, ask whether to generate one."""
        if getattr(self, "_skip_agents_init", False):
            return
        try:
            existing = self.context_manager.find_context_files("AGENTS.md")
        except Exception:
            return
        if existing:
            return
        if self._no_init_marker(self.workspace).exists():
            return

        self.ui.panel(
            "当前工作目录没有 AGENTS.md。\n\n"
            "AGENTS.md 是这个目录专属的「地图」：项目结构 + 硬约束 + 历史教训，"
            "Agent 启动时会自动注入到 system prompt。\n\n"
            "请选择：\n"
            "  [g] 现在生成（扫描目录 + 一次 LLM 调用起草，写入 ./AGENTS.md）\n"
            "  [s] 本次跳过（下次进入该目录时再问）\n"
            "  [n] 永不为该目录生成（写一个标记文件 .jayclaw/.no-agents-md，今后不再问）",
            title="AGENTS.md",
        )
        try:
            from jay_tui.prompt import Prompt
            answer = Prompt().ask(
                "请输入 g=生成 / s=本次跳过 / n=永不",
                choices=["g", "s", "n"],
                default="s",
            ).strip().lower()
        except (KeyboardInterrupt, EOFError):
            self.ui.system("Skipped AGENTS.md initialization.")
            self._skip_agents_init = True
            return
        except Exception as exc:
            self.ui.error(f"Prompt failed: {exc}")
            self._skip_agents_init = True
            return

        if answer == "g":
            self._init_agents_md_now(force=False)
        elif answer == "n":
            try:
                marker = self._no_init_marker(self.workspace)
                marker.parent.mkdir(exist_ok=True)
                marker.write_text("", encoding="utf-8")
                self.ui.system(f"Marker written: {marker}")
            except OSError as exc:
                self.ui.error(f"Failed to write marker: {exc}")
        else:
            self._skip_agents_init = True

    def _init_agents_md_now(self, force: bool = False) -> None:
        """Run the initial AGENTS.md generation. force=True overrides existing AGENTS.md after a confirm."""
        from .agents_md import generate_initial

        target = self.workspace / "AGENTS.md"
        if target.exists() and not force:
            self.ui.error(f"{target} already exists. Use /agents-init to overwrite.")
            return
        if target.exists() and force:
            try:
                from jay_tui.prompt import Prompt
                if not Prompt().confirm(
                    f"Overwrite existing {target}?", default=False
                ):
                    self.ui.system("Cancelled.")
                    return
            except (KeyboardInterrupt, EOFError):
                self.ui.system("Cancelled.")
                return

        self.ui.system("Scanning workspace and asking the LLM for an initial AGENTS.md...")
        import asyncio

        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, generate_initial(self.workspace, self.llm))
                        path = future.result()
                else:
                    path = loop.run_until_complete(generate_initial(self.workspace, self.llm))
            except RuntimeError:
                path = asyncio.run(generate_initial(self.workspace, self.llm))
        except Exception as exc:
            self.ui.error(f"AGENTS.md generation failed: {exc}")
            return

        self.ui.system(f"AGENTS.md written: {path}")

        # Re-inject system prompt so the new AGENTS.md takes effect this session
        try:
            new_prompt = self._get_system_prompt()
            self.agent.system_prompt = new_prompt
            if self.agent.history and self.agent.history[0].role == "system":
                from jay_llm import Message
                self.agent.history[0] = Message(role="system", content=new_prompt)
        except Exception as exc:
            self.ui.error(f"Failed to refresh system prompt (file written, restart to apply): {exc}")

    def _maybe_summarize_to_agents_md(self) -> None:
        """At session end: if AGENTS.md exists and the session had real content, ask whether to append."""
        try:
            existing = self.context_manager.find_context_files("AGENTS.md")
        except Exception:
            return
        if not existing:
            return
        if self._no_summary_marker(self.workspace).exists():
            return

        history = getattr(self.agent, "history", []) or []
        user_turn_count = sum(
            1 for m in history if (getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)) == "user"
        )
        if user_turn_count < 2:
            return

        try:
            from jay_tui.prompt import Prompt
            if not Prompt().confirm(
                "Summarize this session into AGENTS.md?", default=False
            ):
                return
        except (KeyboardInterrupt, EOFError):
            return
        except Exception:
            return

        self._summarize_to_agents_md_now()

    def _summarize_to_agents_md_now(self) -> None:
        """Run an LLM-driven summary and propose updates to AGENTS.md (with diff confirmation)."""
        from .agents_md import append_session_summary

        existing = []
        try:
            existing = self.context_manager.find_context_files("AGENTS.md")
        except Exception:
            logger.exception("find_context_files('AGENTS.md') raised; treating as none")

        target: Path | None = None
        # Prefer workspace-root AGENTS.md if present; fall back to the most-specific found.
        candidate = self.workspace / "AGENTS.md"
        if candidate.is_file():
            target = candidate
        elif existing:
            target = existing[-1]

        if target is None:
            self.ui.error("No AGENTS.md found to summarize into. Run /agents-init first.")
            return

        history = getattr(self.agent, "history", []) or []
        if not history:
            self.ui.error("No conversation history to summarize.")
            return

        self.ui.system("Asking the LLM to extract durable lessons from this session...")
        import asyncio

        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run,
                            append_session_summary(self.workspace, self.llm, history, target),
                        )
                        new_content, diff, parsed = future.result()
                else:
                    new_content, diff, parsed = loop.run_until_complete(
                        append_session_summary(self.workspace, self.llm, history, target)
                    )
            except RuntimeError:
                new_content, diff, parsed = asyncio.run(
                    append_session_summary(self.workspace, self.llm, history, target)
                )
        except FileNotFoundError as exc:
            self.ui.error(str(exc))
            return
        except Exception as exc:
            self.ui.error(f"Session summary skipped: {exc}")
            return

        new_pitfalls = parsed.get("new_pitfalls") or []
        new_constraints = parsed.get("new_constraints") or []

        if not new_pitfalls and not new_constraints:
            self.ui.system("No new durable lessons extracted — AGENTS.md unchanged.")
            return

        summary_lines = []
        if new_constraints:
            summary_lines.append(f"New constraints ({len(new_constraints)}):")
            summary_lines.extend(f"  + {c}" for c in new_constraints)
        if new_pitfalls:
            summary_lines.append(f"New pitfalls ({len(new_pitfalls)}):")
            summary_lines.extend(f"  + {p}" for p in new_pitfalls)
        self.ui.panel("\n".join(summary_lines), title=f"Proposed for {target.name}")

        if diff:
            self.ui.panel(diff, title="Diff")

        try:
            from jay_tui.prompt import Prompt
            if not Prompt().confirm(f"Write changes to {target}?", default=True):
                self.ui.system("Discarded.")
                return
        except (KeyboardInterrupt, EOFError):
            self.ui.system("Discarded.")
            return

        try:
            target.write_text(new_content, encoding="utf-8")
            self.ui.system(f"AGENTS.md updated: {target}")
        except OSError as exc:
            self.ui.error(f"Failed to write {target}: {exc}")

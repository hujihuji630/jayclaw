"""Main Agent class with tool calling and state management."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from jay_llm import LLM, Message, Response

from .context import SystemPromptBuilder
from .memory import InMemoryProvider, MemoryProvider
from .message_queue import MessageQueue
from .models import AgentState
from .observability.events import AgentEventCallback, BillingHook
from .registry import ToolRegistry
from .resilience.profile import ProfileManager
from .resilience.retry import resilient_streaming_call
from .tools import Tool
from .tools.registry import ToolRegistry as EnhancedToolRegistry


class Agent:
    """Agent with LLM and tool calling capabilities."""

    def __init__(
        self,
        name: str = "Agent",
        llm: LLM | None = None,
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 10,
        on_tool_start: Callable | None = None,
        on_tool_end: Callable | None = None,
        verbose: bool = False,
        # Enhanced subsystem parameters
        profile_manager: ProfileManager | None = None,
        event_callback: AgentEventCallback | None = None,
        compress_fn: Callable[[list[Message]], list[Message]] | None = None,
        memory_provider: MemoryProvider | None = None,
        system_prompt_builder: SystemPromptBuilder | None = None,
        billing_hook: BillingHook | None = None,
        max_rounds: int | None = None,
        max_rounds_with_plan: int | None = None,
    ):
        """Initialize agent.

        Args:
            name: Agent name
            llm: LLM client
            tools: List of tools
            system_prompt: System prompt (or base prompt if system_prompt_builder provided)
            max_iterations: Maximum tool calling iterations (deprecated, use max_rounds)
            on_tool_start: Callback when tool starts
            on_tool_end: Callback when tool ends
            verbose: Enable verbose logging
            profile_manager: Optional profile manager for resilience
            event_callback: Optional callback for observability events
            compress_fn: Optional function to compress messages on context overflow
            memory_provider: Optional memory provider for conversation history
            system_prompt_builder: Optional protocol for building system prompts
            billing_hook: Optional hook for tracking costs
            max_rounds: Maximum conversation rounds (replaces max_iterations)
            max_rounds_with_plan: Maximum rounds after plan tool is used
        """
        self.name = name
        self.llm = llm or LLM()
        self.system_prompt = system_prompt
        self.max_iterations = max_rounds or max_iterations  # max_rounds takes precedence
        self.max_rounds_with_plan = max_rounds_with_plan
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.verbose = verbose

        # Enhanced subsystems
        self.profile_manager = profile_manager
        self.event_callback = event_callback
        self.compress_fn = compress_fn
        self.memory_provider = memory_provider or InMemoryProvider()
        self.system_prompt_builder = system_prompt_builder
        self.billing_hook = billing_hook

        # Use ToolRegistry from registry.py (synchronous version)
        self.registry = ToolRegistry()
        # Use EnhancedToolRegistry from tools/registry.py (asynchronous version)
        self.registry_enhanced = EnhancedToolRegistry()

        if tools:
            for tool in tools:
                # Register to simple registry for run()
                self.registry.register(tool)

                # Register to enhanced registry for arun()
                schema = tool.to_openai_schema()
                def make_handler(t):
                    def handler(args, user_id, meta, cancel):
                        return t.execute(**args)
                    return handler
                self.registry_enhanced.register(
                    name=tool.name,
                    handler=make_handler(tool),
                    schema=schema,
                    is_core=True,
                )

        self.history: list[Message] = []
        if system_prompt:
            self.history.append(Message(role="system", content=system_prompt))

        self.message_queue = MessageQueue()
        self._plan_used = False  # Track if plan tool has been used
        self._rounds_since_plan = 0  # Track rounds since plan tool

    def _log(self, message: str, style: str = "") -> None:
        """Log message if verbose.

        Args:
            message: Message to log
            style: Style for message (ignored, kept for compatibility)
        """
        if self.verbose:
            print(message)

    def _clean_content(self, content: str) -> str:
        """Remove thinking tags from content.

        Args:
            content: Raw content from LLM

        Returns:
            Cleaned content without thinking tags
        """
        import re
        # Remove <think>...</think> blocks
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        # Remove orphaned closing tags
        content = re.sub(r'</think>', '', content)
        return content.strip()

    def add_tool(self, tool: Tool) -> None:
        """Add a tool to the agent.

        Args:
            tool: Tool to add
        """
        # Register to both registries
        self.registry.register(tool)

        schema = tool.to_openai_schema()
        def make_handler(t):
            def handler(args, user_id, meta, cancel):
                return t.execute(**args)
            return handler
        self.registry_enhanced.register(
            name=tool.name,
            handler=make_handler(tool),
            schema=schema,
            is_core=True,
        )

    def run(self, message: str, check_queue: bool = True) -> Response:
        """Run agent with a user message (sync wrapper over arun).

        Args:
            message: User message
            check_queue: Check message queue for interrupts

        Returns:
            Agent response
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.arun(message, check_queue))
                    return future.result()
            else:
                return loop.run_until_complete(self.arun(message, check_queue))
        except RuntimeError:
            return asyncio.run(self.arun(message, check_queue))

    async def arun(self, message: str, check_queue: bool = True) -> Response:
        """Async run agent with a user message using enhanced subsystems.

        Uses resilient_streaming_call for LLM calls with retry and fallback.
        Supports context compression, billing tracking, and event emission.

        Args:
            message: User message
            check_queue: Check message queue for interrupts

        Returns:
            Agent response
        """
        self._log(f"User: {message}")
        self.history.append(Message(role="user", content=message))

        iterations = 0
        max_iters = self.max_iterations

        # Check if plan tool was used and apply max_rounds_with_plan
        if self._plan_used and self.max_rounds_with_plan:
            self._rounds_since_plan += 1
            if self._rounds_since_plan > self.max_rounds_with_plan:
                # Inject plan nag
                nag_message = (
                    "You used the plan tool earlier. Please execute the plan or "
                    "provide a final response."
                )
                self._log(f"Plan nag: {nag_message}")
                self.history.append(Message(role="user", content=nag_message))

        while iterations < max_iters:
            iterations += 1
            self._log(f"Iteration {iterations}")

            # Get tool schemas from enhanced registry
            tools_schema = self.registry_enhanced.get_schemas() if len(self.registry_enhanced) > 0 else None

            # Use resilient_streaming_call for LLM call
            response_content = ""
            response_tool_calls = None

            try:
                async for chunk in resilient_streaming_call(
                    llm=self.llm,
                    messages=self.history,
                    profile_manager=self.profile_manager,
                    compress_fn=self.compress_fn,
                    event_callback=self.event_callback,
                    tools=tools_schema,
                ):
                    if chunk.content:
                        response_content += chunk.content
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        response_tool_calls = chunk.tool_calls

                # Track billing if hook provided
                if self.billing_hook and hasattr(chunk, "usage"):
                    self.billing_hook.on_llm_call(
                        model=self.llm.config.model,
                        input_tokens=chunk.usage.get("input_tokens", 0),
                        output_tokens=chunk.usage.get("output_tokens", 0),
                    )

            except Exception as e:
                self._log(f"LLM call failed: {e}")
                raise

            # Check if tool calls are needed
            if response_tool_calls:
                self._log(f"Tool calls requested: {len(response_tool_calls)}")

                # Execute tools
                tool_results = []
                for tool_call in response_tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                    tool_args = json.loads(tool_args_str)

                    self._log(f"→ Calling tool: {tool_name}({tool_args})")

                    # Check if this is the plan tool
                    if tool_name == "plan":
                        self._plan_used = True
                        self._rounds_since_plan = 0

                    if self.on_tool_start:
                        self.on_tool_start(tool_name, tool_args)

                    # Track billing for tool call
                    if self.billing_hook:
                        self.billing_hook.on_tool_call(tool_name=tool_name)

                    try:
                        # Create tool_call object for enhanced registry
                        from types import SimpleNamespace

                        tool_call_obj = SimpleNamespace(
                            function=SimpleNamespace(
                                name=tool_name,
                                arguments=tool_args_str,
                            )
                        )

                        # Use enhanced registry execute, pass registry in meta for discover_tools
                        result = await self.registry_enhanced.execute(
                            tool_call=tool_call_obj,
                            user_id="default",
                            meta={"registry_enhanced": self.registry_enhanced},
                        )

                        # Handle _activate signal from discover_tools
                        if result.ok and isinstance(result.data, dict):
                            activate_list = result.data.get("_activate")
                            if activate_list:
                                newly_activated = self.registry_enhanced.activate_tools(activate_list)
                                if newly_activated:
                                    self._log(f"Activated tools: {newly_activated}")

                        # Build tool result content (strip internal _activate field)
                        if result.ok and isinstance(result.data, dict):
                            display_data = {k: v for k, v in result.data.items() if not k.startswith("_")}
                            tool_content = json.dumps(display_data, ensure_ascii=False)
                        else:
                            tool_content = str(result.data if result.ok else result.error)

                        tool_results.append(
                            {
                                "tool_call_id": tool_call.get("id"),
                                "role": "tool",
                                "name": tool_name,
                                "content": tool_content,
                            }
                        )
                        self._log(f"✓ Result: {tool_content}")

                        if self.on_tool_end:
                            self.on_tool_end(tool_name, result)
                    except Exception as e:
                        error_msg = f"Error: {e}"
                        tool_results.append(
                            {
                                "tool_call_id": tool_call.get("id"),
                                "role": "tool",
                                "name": tool_name,
                                "content": error_msg,
                            }
                        )
                        self._log(f"✗ {error_msg}")

                # Add assistant message and tool results to history
                self.history.append(
                    Message(
                        role="assistant",
                        content=response_content or "",
                        metadata={"tool_calls": response_tool_calls},
                    )
                )
                for tool_result in tool_results:
                    self.history.append(
                        Message(
                            role="tool",
                            content=tool_result["content"],
                            metadata={
                                "tool_call_id": tool_result["tool_call_id"],
                                "name": tool_result["name"],
                            },
                        )
                    )

                # Check for steering messages after tool execution
                if check_queue and self.message_queue.has_steering():
                    steering = self.message_queue.get_steering_messages()
                    for msg in steering:
                        self._log(f"⚡ Steering: {msg.content}")
                        self.history.append(Message(role="user", content=msg.content))

                # Continue loop to get final response
                continue
            else:
                # No tool calls, we have final response
                cleaned_content = self._clean_content(response_content)
                self.history.append(Message(role="assistant", content=cleaned_content))
                self._log(f"Agent: {cleaned_content}")

                # Check for follow-up messages
                if check_queue and self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    if followup:
                        # Process first follow-up recursively
                        self._log(f"→ Follow-up: {followup[0].content}")
                        return await self.arun(followup[0].content, check_queue=True)

                return Response(
                    content=cleaned_content,
                    model=self.llm.config.model,
                )

        # Max iterations reached
        final_response = Response(
            content="Maximum iterations reached without completion.",
            model=self.llm.config.model,
        )
        self.history.append(Message(role="assistant", content=final_response.content))
        return final_response

    def get_state(self) -> AgentState:
        """Get current agent state.

        Returns:
            Agent state
        """
        return AgentState(
            name=self.name,
            system_prompt=self.system_prompt,
            messages=[msg.model_dump() for msg in self.history],
        )

    def save_state(self, path: str | Path) -> None:
        """Save agent state to file.

        Args:
            path: File path to save state
        """
        state = self.get_state()
        Path(path).write_text(state.model_dump_json(indent=2))

    @classmethod
    def from_state(cls, path: str | Path, llm: LLM | None = None) -> "Agent":
        """Load agent from saved state.

        Args:
            path: File path to load state from
            llm: LLM client (required)

        Returns:
            Agent instance
        """
        state_json = Path(path).read_text()
        state = AgentState.model_validate_json(state_json)

        agent = cls(
            name=state.name,
            llm=llm,
            system_prompt=state.system_prompt,
        )

        # Restore history
        agent.history = [Message(**msg) for msg in state.messages]

        return agent

    def clear_history(self) -> None:
        """Clear conversation history (keeps system prompt)."""
        if self.system_prompt:
            self.history = [Message(role="system", content=self.system_prompt)]
        else:
            self.history = []

    async def respond(
        self,
        message: str,
        cancel: asyncio.Event | None = None,
    ) -> str:
        """Non-streaming respond method that collects all chunks.

        Args:
            message: User message
            cancel: Optional cancellation event

        Returns:
            Complete agent response as string
        """
        chunks = []
        async for chunk in self.respond_stream(message, cancel):
            chunks.append(chunk)
        return "".join(chunks)

    async def respond_stream(
        self,
        message: str,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Streaming respond method that yields text chunks.

        Args:
            message: User message
            cancel: Optional cancellation event

        Yields:
            Text chunks from the agent response
        """
        self._log(f"[bold blue]User:[/bold blue] {message}")
        self.history.append(Message(role="user", content=message))

        async for chunk in self._master_loop(cancel):
            yield chunk

    async def _master_loop(
        self,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Streaming master loop — delegates to arun() for unified tool execution.

        Args:
            cancel: Optional cancellation event

        Yields:
            Text chunks from the final agent response
        """
        # Pop the last user message that respond_stream already appended
        last_user_msg = ""
        if self.history and self.history[-1].role == "user":
            last_user_msg = self.history.pop().content

        response = await self.arun(last_user_msg)
        for char in response.content:
            if cancel and cancel.is_set():
                return
            yield char

    async def _execute_tool_calls_from_dict(
        self,
        tool_calls: list[dict[str, Any]],
        cancel: asyncio.Event | None = None,
    ) -> None:
        """Execute tool calls from dictionary format.

        Args:
            tool_calls: List of tool call dictionaries
            cancel: Optional cancellation event
        """
        for tool_call in tool_calls:
            if cancel and cancel.is_set():
                return

            tool_name = tool_call.get("function", {}).get("name")
            tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
            tool_call_id = tool_call.get("id")

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            self._log(f"[cyan]→ Calling tool: {tool_name}({tool_args})[/cyan]")

            if self.on_tool_start:
                self.on_tool_start(tool_name, tool_args)

            try:
                result = self.registry.execute(tool_name, **tool_args)
                self.history.append(
                    Message(
                        role="tool",
                        content=str(result),
                        metadata={
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                        },
                    )
                )
                self._log(f"[green]✓ Result: {result}[/green]")

                if self.on_tool_end:
                    self.on_tool_end(tool_name, result)
            except Exception as e:
                error_msg = f"Error: {e}"
                self.history.append(
                    Message(
                        role="tool",
                        content=error_msg,
                        metadata={
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                        },
                    )
                )
                self._log(f"[red]✗ {error_msg}[/red]")

    async def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        """Execute tool calls (backward compatibility wrapper).

        Args:
            tool_calls: List of tool call dictionaries
        """
        await self._execute_tool_calls_from_dict(tool_calls, None)

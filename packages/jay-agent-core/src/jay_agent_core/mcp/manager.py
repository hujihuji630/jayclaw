"""MCP Manager: server lifecycle and tool bridging into ToolRegistry."""

import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Any

from .client import MCPClient
from .config import MCPServerConfig, load_mcp_config, save_mcp_config

logger = logging.getLogger(__name__)


class MCPServerStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class MCPServerInfo:
    __slots__ = ("name", "config", "client", "status", "tools", "error")

    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self.client: MCPClient | None = None
        self.status: MCPServerStatus = MCPServerStatus.STOPPED
        self.tools: list[dict] = []
        self.error: str | None = None


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._servers: dict[str, MCPServerInfo] = {}

    async def load_and_start(self) -> None:
        configs = load_mcp_config(self._workspace)
        for name, cfg in configs.items():
            self._servers[name] = MCPServerInfo(name, cfg)
        await asyncio.gather(
            *(self.start_server(n) for n in self._servers),
            return_exceptions=True,
        )

    async def start_server(self, name: str) -> None:
        info = self._servers.get(name)
        if not info:
            return
        info.status = MCPServerStatus.STARTING
        info.error = None
        try:
            client = MCPClient(info.config.command, info.config.args, info.config.env)
            await client.start()
            info.client = client
            result = await client.request("tools/list")
            info.tools = result.get("tools", [])
            info.status = MCPServerStatus.RUNNING
            logger.info("MCP server '%s' started with %d tools", name, len(info.tools))
        except Exception as e:
            info.status = MCPServerStatus.ERROR
            info.error = str(e)
            logger.warning("MCP server '%s' failed to start: %s", name, e)

    async def stop_server(self, name: str) -> None:
        info = self._servers.get(name)
        if not info or not info.client:
            return
        await info.client.stop()
        info.client = None
        info.status = MCPServerStatus.STOPPED
        info.tools = []

    async def restart_server(self, name: str) -> None:
        await self.stop_server(name)
        await self.start_server(name)

    async def add_server(self, name: str, config: MCPServerConfig) -> None:
        self._servers[name] = MCPServerInfo(name, config)
        self._save_config()
        await self.start_server(name)

    async def remove_server(self, name: str) -> None:
        await self.stop_server(name)
        self._servers.pop(name, None)
        self._save_config()

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        info = self._servers.get(server_name)
        if not info or not info.client or not info.client.is_running:
            raise ConnectionError(f"MCP server '{server_name}' is not running")
        result = await info.client.request("tools/call", {"name": tool_name, "arguments": arguments})
        return result

    def register_tools(self, registry) -> list[str]:
        """Register all discovered MCP tools into a ToolRegistry. Returns registered names."""
        from ..tools.base import ToolResult

        registered: list[str] = []
        for info in self._servers.values():
            if info.status != MCPServerStatus.RUNNING:
                continue
            for tool in info.tools:
                tool_name = f"mcp_{info.name}_{tool['name']}"
                schema = {
                    "type": "function",
                    "_permission": "read",
                    "function": {
                        "name": tool_name,
                        "description": tool.get("description", f"MCP tool from {info.name}"),
                        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                    },
                }
                server_name = info.name
                orig_name = tool["name"]

                def _make_handler(sn, tn):
                    async def handler(args, user_id=None, meta=None, cancel=None):
                        try:
                            result = await self.call_tool(sn, tn, args)
                            content = result.get("content", [])
                            text = "\n".join(
                                c.get("text", "") for c in content if c.get("type") == "text"
                            )
                            return ToolResult(ok=True, data=text or str(result))
                        except Exception as e:
                            return ToolResult(ok=False, error=str(e))
                    return handler

                registry.register(
                    name=tool_name,
                    handler=_make_handler(server_name, orig_name),
                    schema=schema,
                    is_core=True,
                    timeout=60.0,
                )
                registered.append(tool_name)
        return registered

    def get_status(self) -> list[dict]:
        return [
            {
                "name": info.name,
                "status": info.status.value,
                "tools": [{"name": t["name"], "description": t.get("description", "")} for t in info.tools],
                "error": info.error,
            }
            for info in self._servers.values()
        ]

    async def shutdown(self) -> None:
        await asyncio.gather(
            *(self.stop_server(n) for n in list(self._servers)),
            return_exceptions=True,
        )

    def _save_config(self) -> None:
        configs = {name: info.config for name, info in self._servers.items()}
        save_mcp_config(self._workspace, configs)

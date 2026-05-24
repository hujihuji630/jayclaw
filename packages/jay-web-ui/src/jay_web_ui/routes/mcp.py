"""MCP server management endpoints."""

from __future__ import annotations

from fastapi import Request


def register(server) -> None:
    """Mount MCP endpoints onto ``server.app``."""

    def _get_mcp_manager():
        if server.agent and hasattr(server.agent, "mcp_manager"):
            return server.agent.mcp_manager
        return None

    @server.app.get("/api/mcp/servers")
    async def list_mcp_servers():
        mgr = _get_mcp_manager()
        if not mgr:
            return {"servers": []}
        return {"servers": mgr.get_status()}

    @server.app.post("/api/mcp/servers")
    async def add_mcp_server(request: Request):
        mgr = _get_mcp_manager()
        if not mgr:
            return {"status": "error", "error": "MCP not available"}
        body = await request.json()
        name = body.get("name", "").strip()
        command = body.get("command", "").strip()
        if not name or not command:
            return {"status": "error", "error": "name and command are required"}

        from jay_agent_core.mcp import MCPServerConfig
        config = MCPServerConfig(
            command=command,
            args=body.get("args", []),
            env=body.get("env", {}),
        )
        await mgr.add_server(name, config)
        mgr.register_tools(server.agent.agent.registry_enhanced)
        info = next((s for s in mgr.get_status() if s["name"] == name), None)
        return {"status": "ok", "server": info}

    @server.app.delete("/api/mcp/servers/{name}")
    async def remove_mcp_server(name: str):
        mgr = _get_mcp_manager()
        if not mgr:
            return {"status": "error", "error": "MCP not available"}
        await mgr.remove_server(name)
        return {"status": "ok"}

    @server.app.post("/api/mcp/servers/{name}/restart")
    async def restart_mcp_server(name: str):
        mgr = _get_mcp_manager()
        if not mgr:
            return {"status": "error", "error": "MCP not available"}
        await mgr.restart_server(name)
        mgr.register_tools(server.agent.agent.registry_enhanced)
        info = next((s for s in mgr.get_status() if s["name"] == name), None)
        return {"status": "ok", "server": info}

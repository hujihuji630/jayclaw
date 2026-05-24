"""MCP server configuration: load/save .jayclaw/mcp.json."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import DIR_NAME, global_dir


@dataclass
class MCPServerConfig:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def _config_path(workspace: Path) -> Path:
    return workspace / DIR_NAME / "mcp.json"


def load_mcp_config(workspace: Path) -> dict[str, MCPServerConfig]:
    """Load MCP config, merging global and project (project wins)."""
    servers: dict[str, MCPServerConfig] = {}
    for path in [global_dir() / "mcp.json", _config_path(workspace)]:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for name, cfg in data.get("mcpServers", {}).items():
                    servers[name] = MCPServerConfig(
                        command=cfg["command"],
                        args=cfg.get("args", []),
                        env=cfg.get("env", {}),
                    )
            except (json.JSONDecodeError, KeyError):
                continue
    return servers


def save_mcp_config(workspace: Path, servers: dict[str, MCPServerConfig]) -> None:
    """Save MCP config to project .jayclaw/mcp.json."""
    path = _config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "mcpServers": {
            name: {"command": cfg.command, "args": cfg.args, "env": cfg.env}
            for name, cfg in servers.items()
        }
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

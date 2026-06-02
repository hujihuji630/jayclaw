"""Workspace + directory-browsing endpoints (whitelist-enforced)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import string
import sys
from pathlib import Path

from fastapi import HTTPException, Request

from jay_web_ui.security import (
    _allowed_workspace_roots,
    _check_workspace_path,
    _is_system_path,
    _is_under_allowed_root,
)

logger = logging.getLogger(__name__)


def register(server) -> None:
    """Mount workspace endpoints onto ``server.app``."""

    @server.app.get("/api/workspace")
    async def get_workspace():
        if server.agent and hasattr(server.agent, "workspace"):
            return {"workspace": str(server.agent.workspace)}
        return {"workspace": str(Path.cwd())}

    @server.app.post("/api/workspace")
    async def set_workspace(request: Request):
        body = await request.json()
        new_path = body.get("path", "").strip()
        if not new_path:
            return {"status": "error", "error": "path is required"}
        try:
            checked = _check_workspace_path(new_path)
        except HTTPException as exc:
            return {"status": "error", "error": exc.detail}
        try:
            if hasattr(server.agent, "change_workspace"):
                resolved = server.agent.change_workspace(str(checked))
            elif hasattr(server.agent, "agent") and hasattr(server.agent.agent, "change_workspace"):
                resolved = server.agent.change_workspace(str(checked))
            else:
                return {"status": "error", "error": "Agent does not support workspace change"}

            # Reload MCP servers from new workspace
            if hasattr(server.agent, "mcp_manager") and server.agent.mcp_manager:
                mgr = server.agent.mcp_manager
                await mgr.shutdown()
                await mgr.load_and_start()
                core = server.agent.agent if hasattr(server.agent, "agent") else server.agent
                if hasattr(core, "registry_enhanced"):
                    mgr.register_tools(core.registry_enhanced)

            return {"status": "ok", "workspace": resolved}
        except ValueError as e:
            return {"status": "error", "error": str(e)}

    @server.app.get("/api/browse/native")
    async def browse_native():
        """Open a native OS directory picker and return the chosen path.

        Refuses to launch unless the server is bound to ``127.0.0.1`` /
        ``localhost`` — this endpoint blocks the host's GUI thread for up
        to 120s and shouldn't be exposed to LAN/public clients.
        """
        if server.host not in ("127.0.0.1", "localhost", "::1"):
            return {
                "status": "error",
                "error": "/api/browse/native is only available when binding to 127.0.0.1",
            }

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
            if not path:
                return {"status": "cancelled"}
            try:
                checked = _check_workspace_path(path)
            except HTTPException as exc:
                return {"status": "error", "error": exc.detail}
            return {"status": "ok", "path": str(checked)}
        except Exception as e:
            logger.exception("native browse failed")
            return {"status": "error", "error": str(e)}

    @server.app.get("/api/browse")
    async def browse_dirs(path: str = ""):
        """Return subdirectories of a given path for the directory picker.

        Honors the workspace whitelist: only paths inside ~ / cwd /
        $WEB_UI_WORKSPACE_ROOTS are listable; system paths are refused.
        Drive-root listing on Windows is always allowed (it's the entry
        point for users to navigate to whitelisted directories).
        """
        if not path:
            roots = _allowed_workspace_roots()
            if os.name == "nt":
                drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
                allowed_drives = [
                    d for d in drives
                    if any(str(r).lower().startswith(d.lower()) for r in roots)
                ]
                if allowed_drives:
                    return {"path": "", "dirs": allowed_drives, "parent": None}
            return {
                "path": "",
                "dirs": [str(r) for r in roots],
                "parent": None,
            }

        try:
            checked = _check_workspace_path(path)
        except HTTPException as exc:
            return {"error": exc.detail}

        if not checked.is_dir():
            return {"error": f"Not a directory: {checked}"}

        try:
            dirs = sorted(
                [str(child) for child in checked.iterdir()
                 if child.is_dir() and not child.name.startswith(".")],
                key=lambda x: x.lower(),
            )
        except PermissionError:
            dirs = []

        parent_path = checked.parent
        if parent_path == checked:
            parent = None
        elif _is_system_path(parent_path) or not _is_under_allowed_root(parent_path):
            parent = None
        else:
            parent = str(parent_path)

        return {"path": str(checked), "dirs": dirs, "parent": parent}

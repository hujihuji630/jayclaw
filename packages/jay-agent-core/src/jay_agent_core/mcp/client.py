"""MCP JSON-RPC 2.0 client over stdio transport."""

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    """Low-level MCP client communicating via subprocess stdin/stdout."""

    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None):
        self._command = command
        self._args = args or []
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: asyncio.Task | None = None
        self._server_capabilities: dict = {}

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """Spawn the MCP server process and perform the initialize handshake."""
        import shutil

        env = {**os.environ, **(self._env or {})}
        command = shutil.which(self._command) or self._command
        self._process = await asyncio.create_subprocess_exec(
            command, *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._read_task = asyncio.create_task(self._read_loop())
        result = await self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "jayclaw", "version": "1.0"},
        })
        self._server_capabilities = result.get("capabilities", {})
        await self._notify("notifications/initialized")

    async def stop(self) -> None:
        """Terminate the server process."""
        if not self._process:
            return
        if self._read_task:
            self._read_task.cancel()
        try:
            self._process.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            self._process.kill()
        self._process = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("MCP server stopped"))
        self._pending.clear()

    async def request(self, method: str, params: dict | None = None) -> Any:
        """Send a JSON-RPC request and await the response."""
        self._request_id += 1
        msg_id = self._request_id
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self._send(msg)
        try:
            return await asyncio.wait_for(fut, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"MCP request {method} timed out")

    async def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._send(msg)

    async def _send(self, msg: dict) -> None:
        if not self._process or not self._process.stdin:
            raise ConnectionError("MCP server not running")
        data = json.dumps(msg) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from stdout."""
        assert self._process and self._process.stdout
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if "error" in msg:
                        fut.set_exception(RuntimeError(
                            f"MCP error: {msg['error'].get('message', msg['error'])}"
                        ))
                    else:
                        fut.set_result(msg.get("result", {}))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("MCP read loop error: %s", e)

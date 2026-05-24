"""File upload, listing, deletion endpoints."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from fastapi import File, HTTPException, Request, UploadFile

from jay_web_ui.security import _safe_join

logger = logging.getLogger(__name__)


def register(server) -> None:
    """Mount file endpoints onto ``server.app``."""

    @server.app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...)):
        """Handle file upload — saves to workspace/.uploads/.

        The client-supplied filename is stripped of any directory components
        (``../foo`` becomes ``foo``) and the resolved path is asserted to
        stay inside ``workspace/.uploads/``.
        """
        try:
            workspace = Path.cwd()
            if server.agent and hasattr(server.agent, "workspace"):
                workspace = Path(server.agent.workspace)
            upload_dir = workspace / ".uploads"
            upload_dir.mkdir(exist_ok=True)

            file_path = _safe_join(upload_dir, file.filename or "")

            content = await file.read()
            file_path.write_bytes(content)

            return {
                "status": "ok",
                "filename": file_path.name,
                "size": len(content),
                "path": str(file_path.relative_to(workspace)),
                "type": file.content_type or "application/octet-stream",
            }
        except HTTPException:
            raise
        except OSError as exc:
            logger.exception("upload failed")
            return {"status": "error", "error": f"写入失败: {exc}"}

    @server.app.get("/api/files")
    async def list_files():
        """List uploaded files in workspace/.uploads/."""
        workspace = Path.cwd()
        if server.agent and hasattr(server.agent, "workspace"):
            workspace = Path(server.agent.workspace)
        upload_dir = workspace / ".uploads"
        if not upload_dir.exists():
            return {"files": []}
        files = []
        for f in sorted(upload_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                stat = f.stat()
                mime, _ = mimetypes.guess_type(str(f))
                files.append({
                    "filename": f.name,
                    "path": str(f.relative_to(workspace)),
                    "size": stat.st_size,
                    "type": mime or "application/octet-stream",
                    "modified": stat.st_mtime,
                })
        return {"files": files}

    @server.app.delete("/api/files")
    async def delete_file(request: Request):
        """Delete an uploaded file. Filename is sanitized to prevent path traversal."""
        body = await request.json()
        filename = (body.get("filename") or "").strip()
        workspace = Path.cwd()
        if server.agent and hasattr(server.agent, "workspace"):
            workspace = Path(server.agent.workspace)
        upload_dir = workspace / ".uploads"
        try:
            file_path = _safe_join(upload_dir, filename)
        except HTTPException as exc:
            return {"status": "error", "error": exc.detail}
        if not file_path.is_file():
            return {"status": "error", "error": "文件不存在"}
        try:
            file_path.unlink()
            return {"status": "ok"}
        except OSError as e:
            return {"status": "error", "error": str(e)}

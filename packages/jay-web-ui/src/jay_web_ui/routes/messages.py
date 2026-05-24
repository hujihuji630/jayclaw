"""Message-level mutation endpoints (truncate; future: pin, archive)."""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel


class TruncateRequest(BaseModel):
    after_id: str


def register(server) -> None:
    """Mount message endpoints onto ``server.app``."""

    @server.app.post("/api/messages/truncate")
    async def truncate(req: TruncateRequest):
        """Remove every message strictly after the message with ``after_id``."""
        target = req.after_id
        idx = next(
            (i for i, m in enumerate(server.history) if m.id == target),
            None,
        )
        if idx is None:
            raise HTTPException(status_code=400, detail=f"unknown message id: {target}")

        keep = server.history[: idx + 1]
        removed = len(server.history) - len(keep)
        server.history[:] = keep

        # Mirror into core agent's history if present. The core agent's history
        # may interleave system / tool messages, so we cut by id when available
        # and fall back to a role-aware index alignment otherwise.
        core = getattr(server.agent, "agent", None) if server.agent else None
        if core is not None and getattr(core, "history", None) is not None:
            core_hist = core.history
            if core_hist and all(getattr(m, "id", None) for m in core_hist):
                cidx = next(
                    (i for i, m in enumerate(core_hist) if m.id == target),
                    None,
                )
                if cidx is not None:
                    del core_hist[cidx + 1:]
            else:
                want_user = sum(1 for m in keep if m.role == "user")
                want_asst = sum(1 for m in keep if m.role == "assistant")
                seen_user = seen_asst = 0
                cut_at = len(core_hist)
                for i, m in enumerate(core_hist):
                    if m.role == "user":
                        seen_user += 1
                    elif m.role == "assistant":
                        seen_asst += 1
                    if seen_user >= want_user and seen_asst >= want_asst:
                        cut_at = i + 1
                        break
                del core_hist[cut_at:]

        # Best-effort session persistence.
        if server.agent and hasattr(server.agent, "session"):
            try:
                server.agent.session.save()
            except Exception:
                pass

        return {"removed": removed}

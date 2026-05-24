"""Data models for web UI."""

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _gen_id() -> str:
    """uuid4 hex — matches the convention used in jay_agent_core.memory.Message."""
    return uuid4().hex


class ChatMessage(BaseModel):
    """A chat message."""

    id: str = Field(default_factory=_gen_id)
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str | None = None


class ChatRequest(BaseModel):
    """Chat request from client."""

    message: str
    attachments: list[dict[str, Any]] | None = None
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Chat response to client."""

    content: str
    role: Literal["assistant"] = "assistant"
    conversation_id: str | None = None


class StreamChunk(BaseModel):
    """Streaming response chunk."""

    type: Literal["start", "token", "done", "error", "status"]
    content: str | None = None
    error: str | None = None
    status: str | None = None

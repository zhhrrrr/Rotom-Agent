from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RunChunkType = Literal[
    "message_delta",
    "message_final",
    "tool_started",
    "tool_delta",
    "tool_finished",
    "status",
    "error",
]


class RunChunkCreate(BaseModel):
    run_id: str
    user_id: str
    workspace_id: str
    session_id: str
    chunk_type: RunChunkType
    content: str = ""
    role: str | None = Field(default=None, max_length=32)
    payload: dict[str, Any] | None = None
    is_final: bool = False


class RunChunkRead(BaseModel):
    id: str
    run_id: str
    user_id: str
    workspace_id: str
    session_id: str
    chunk_index: int
    chunk_type: RunChunkType
    role: str | None
    content: str
    payload: dict[str, Any] | None
    is_final: bool
    created_at: datetime

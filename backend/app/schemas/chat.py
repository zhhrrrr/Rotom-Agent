from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    workspace_id: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    user_id: str
    workspace_id: str
    session_id: str
    run_id: str
    status: str


class RunDebugResponse(BaseModel):
    run: dict[str, Any]
    messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    model_calls: list[dict[str, Any]]
    event_logs: list[dict[str, Any]]

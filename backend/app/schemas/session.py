from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="New Session", min_length=1, max_length=200)


class SessionResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionMessageResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    session_id: str
    run_id: str | None
    role: str
    content: str
    meta: dict
    created_at: datetime


class SessionRunResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    session_id: str
    user_input: str
    status: str
    current_step: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class SessionToolCallResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    run_id: str
    tool_name: str
    tool_args: dict
    tool_result: dict | None
    status: str
    runtime_type: str | None
    risk_level: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: list[SessionMessageResponse]
    runs: list[SessionRunResponse] = []
    tool_calls: list[SessionToolCallResponse] = []
    has_more: bool = False
    next_before: datetime | None = None

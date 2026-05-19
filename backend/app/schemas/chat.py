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


class RunResponse(BaseModel):
    run_id: str
    user_id: str
    workspace_id: str
    session_id: str
    status: str
    error: str | None
    answer: str | None

from datetime import datetime

from pydantic import BaseModel, Field


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceResponse(BaseModel):
    id: str
    user_id: str
    name: str
    root_path: str
    created_at: datetime
    updated_at: datetime

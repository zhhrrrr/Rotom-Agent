from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import get_session
from app.db.models import User, Workspace
from app.schemas import CreateWorkspaceRequest, WorkspaceResponse
from app.services import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceResponse:
    workspace = await WorkspaceService(db).create_workspace(
        user_id=current_user.id,
        name=request.name,
    )
    return _workspace_response(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[WorkspaceResponse]:
    workspaces = await WorkspaceService(db).list_workspaces(current_user.id)
    return [_workspace_response(workspace) for workspace in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceResponse:
    workspace = await WorkspaceService(db).get_owned_workspace(
        user_id=current_user.id,
        workspace_id=workspace_id,
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    await WorkspaceService(db).ensure_workspace_path(workspace)
    return _workspace_response(workspace)


def _workspace_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        user_id=workspace.user_id,
        name=workspace.name,
        root_path=workspace.root_path,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )

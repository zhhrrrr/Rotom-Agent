from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import get_session
from app.db.models import Message, Session as SessionModel, User
from app.schemas import (
    CreateSessionRequest,
    SessionDetailResponse,
    SessionMessageResponse,
    SessionResponse,
)
from app.services import MessageService, SessionService, WorkspaceService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    workspace_id: Annotated[str, Query(min_length=1, max_length=64)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[SessionResponse]:
    workspace = await WorkspaceService(db).get_owned_workspace(
        user_id=current_user.id,
        workspace_id=workspace_id,
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    sessions = await SessionService(db).list_workspace_sessions(
        user_id=current_user.id,
        workspace_id=workspace_id,
    )
    return [_session_response(session) for session in sessions]


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> SessionResponse:
    workspace = await WorkspaceService(db).get_owned_workspace(
        user_id=current_user.id,
        workspace_id=request.workspace_id,
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    session = await SessionService(db).create_session(
        user_id=current_user.id,
        workspace_id=workspace.id,
        title=request.title,
    )
    return _session_response(session)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> SessionDetailResponse:
    session = await SessionService(db).get_session(session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await MessageService(db).list_session_messages(session.id)
    return SessionDetailResponse(
        session=_session_response(session),
        messages=[_message_response(message) for message in messages],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    try:
        deleted = await SessionService(db).delete_owned_session(
            user_id=current_user.id,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


def _session_response(session: SessionModel) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        workspace_id=session.workspace_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _message_response(message: Message) -> SessionMessageResponse:
    return SessionMessageResponse(
        id=message.id,
        user_id=message.user_id,
        workspace_id=message.workspace_id,
        session_id=message.session_id,
        run_id=message.run_id,
        role=message.role,
        content=message.content,
        meta=message.meta,
        created_at=message.created_at,
    )

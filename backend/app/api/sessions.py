from typing import Annotated

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import get_session
from app.db.models import Message, Run, Session as SessionModel, ToolCall, User
from app.schemas import (
    CreateSessionRequest,
    SessionDetailResponse,
    SessionMessageResponse,
    SessionResponse,
    SessionRunResponse,
    SessionToolCallResponse,
)
from app.services import SessionService, WorkspaceService

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
    before: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> SessionDetailResponse:
    session = await SessionService(db).get_session(session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    runs, has_more = await _list_session_runs(db, session.id, before=before, limit=limit)
    run_ids = [run.id for run in runs]
    messages = await _list_session_messages(db, run_ids)
    tool_calls = await _list_session_tool_calls(db, run_ids)
    return SessionDetailResponse(
        session=_session_response(session),
        messages=[_message_response(message) for message in messages],
        runs=[_run_response(run) for run in runs],
        tool_calls=[_tool_call_response(tool_call) for tool_call in tool_calls],
        has_more=has_more,
        next_before=runs[0].created_at if runs else None,
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


async def _list_session_runs(
    db: AsyncSession,
    session_id: str,
    before: datetime | None,
    limit: int,
) -> tuple[list[Run], bool]:
    stmt = select(Run).where(Run.session_id == session_id)
    if before is not None:
        stmt = stmt.where(Run.created_at < before)

    result = await db.execute(
        stmt.order_by(Run.created_at.desc()).limit(limit + 1)
    )
    rows = list(result.scalars().all())
    return list(reversed(rows[:limit])), len(rows) > limit


async def _list_session_messages(db: AsyncSession, run_ids: list[str]) -> list[Message]:
    if not run_ids:
        return []

    result = await db.execute(
        select(Message)
        .where(Message.run_id.in_(run_ids))
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def _list_session_tool_calls(db: AsyncSession, run_ids: list[str]) -> list[ToolCall]:
    if not run_ids:
        return []

    result = await db.execute(
        select(ToolCall)
        .where(ToolCall.run_id.in_(run_ids))
        .order_by(ToolCall.created_at.asc())
    )
    return list(result.scalars().all())


def _run_response(run: Run) -> SessionRunResponse:
    return SessionRunResponse(
        id=run.id,
        user_id=run.user_id,
        workspace_id=run.workspace_id,
        session_id=run.session_id,
        user_input=run.user_input,
        status=run.status,
        current_step=run.current_step,
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        finished_at=run.finished_at,
    )


def _tool_call_response(tool_call: ToolCall) -> SessionToolCallResponse:
    return SessionToolCallResponse(
        id=tool_call.id,
        user_id=tool_call.user_id,
        workspace_id=tool_call.workspace_id,
        run_id=tool_call.run_id,
        tool_name=tool_call.tool_name,
        tool_args=tool_call.tool_args,
        tool_result=tool_call.tool_result,
        status=tool_call.status,
        runtime_type=tool_call.runtime_type,
        risk_level=tool_call.risk_level,
        error=tool_call.error,
        created_at=tool_call.created_at,
        finished_at=tool_call.finished_at,
    )

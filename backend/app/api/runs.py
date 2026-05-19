import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import AsyncSessionLocal, get_session
from app.db.models import Run, RunChunk, User
from app.schemas import RunChunkRead
from app.services import ChunkService, RunService


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "timeout"}
SSE_POLL_INTERVAL_SECONDS = 0.5

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}/chunks", response_model=list[RunChunkRead])
async def list_run_chunks(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    after: Annotated[int | None, Query(ge=-1)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[RunChunkRead]:
    await _get_owned_run_or_404(db, current_user.id, run_id)
    chunks = await ChunkService(db).list_chunks(
        run_id=run_id,
        after_index=after,
        limit=limit,
    )
    return [_chunk_read(chunk) for chunk in chunks]


@router.get("/{run_id}/stream")
async def stream_run_chunks(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    after: Annotated[int | None, Query(ge=-1)] = None,
) -> StreamingResponse:
    await _get_owned_run_or_404(db, current_user.id, run_id)
    return StreamingResponse(
        _run_chunk_events(
            run_id=run_id,
            user_id=current_user.id,
            after_index=after,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_chunk_events(
    run_id: str,
    user_id: str,
    after_index: int | None,
) -> AsyncGenerator[str, None]:
    last_index = after_index if after_index is not None else -1

    while True:
        async with AsyncSessionLocal() as db:
            run = await RunService(db).get_owned_run(user_id=user_id, run_id=run_id)
            if run is None:
                yield _sse_event(
                    "error",
                    {
                        "run_id": run_id,
                        "error": "Run not found",
                    },
                )
                return

            chunks = await ChunkService(db).list_chunks(
                run_id=run_id,
                after_index=last_index,
            )
            for chunk in chunks:
                last_index = chunk.chunk_index
                yield _sse_event("chunk", _chunk_payload(chunk))

            if run.status in TERMINAL_RUN_STATUSES:
                yield _sse_event(
                    "done",
                    {
                        "run_id": run.id,
                        "status": run.status,
                    },
                )
                return

        await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)


async def _get_owned_run_or_404(db: AsyncSession, user_id: str, run_id: str) -> Run:
    run = await RunService(db).get_owned_run(user_id=user_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _chunk_read(chunk: RunChunk) -> RunChunkRead:
    return RunChunkRead(
        id=chunk.id,
        run_id=chunk.run_id,
        user_id=chunk.user_id,
        workspace_id=chunk.workspace_id,
        session_id=chunk.session_id,
        chunk_index=chunk.chunk_index,
        chunk_type=chunk.chunk_type,
        role=chunk.role,
        content=chunk.content,
        payload=chunk.payload,
        is_final=chunk.is_final,
        created_at=chunk.created_at,
    )


def _chunk_payload(chunk: RunChunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "run_id": chunk.run_id,
        "user_id": chunk.user_id,
        "workspace_id": chunk.workspace_id,
        "session_id": chunk.session_id,
        "chunk_index": chunk.chunk_index,
        "chunk_type": chunk.chunk_type,
        "role": chunk.role,
        "content": chunk.content,
        "payload": chunk.payload,
        "is_final": chunk.is_final,
        "created_at": chunk.created_at.isoformat(),
    }


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

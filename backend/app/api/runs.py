import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import AsyncSessionLocal, get_session
from app.db.models import Run, User
from app.services import RunService
from app.streaming import RunStreamSubscription

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "timeout"}

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    await _get_owned_run_or_404(db, current_user.id, run_id)

    return StreamingResponse(
        _run_stream_events(run_id=run_id, user_id=current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_stream_events(run_id: str, user_id: str) -> AsyncGenerator[str, None]:
    subscription = await RunStreamSubscription.create(run_id)
    try:
        while True:
            event = await subscription.get(timeout=0.5)
            if event is not None:
                yield _sse_event("run_event", event)
                continue

            async with AsyncSessionLocal() as db:
                run = await RunService(db).get_owned_run(user_id=user_id, run_id=run_id)
                if run is None:
                    yield _sse_event("error", {"run_id": run_id, "error": "Run not found"})
                    return
                if run.status in TERMINAL_RUN_STATUSES:
                    yield _sse_event("done", {"run_id": run.id, "status": run.status})
                    return
    finally:
        await subscription.close()


async def _get_owned_run_or_404(
    db: AsyncSession,
    user_id: str,
    run_id: str,
) -> Run:
    run = await RunService(db).get_owned_run(user_id=user_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )

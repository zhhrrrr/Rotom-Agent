from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run
from app.gateway.request_context import RequestContext
from app.services import RunService


class RunRouter:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.run_service = RunService(db)

    async def ensure_no_active_run(self, context: RequestContext) -> None:
        if context.session is None:
            raise RuntimeError("Session must be resolved before active run check")

        active_run = await self.run_service.get_active_run(context.session.id)
        if active_run is not None:
            raise HTTPException(
                status_code=409,
                detail="current session already has a running run",
            )

    async def create_run(self, context: RequestContext) -> Run:
        if context.workspace is None or context.session is None:
            raise RuntimeError("Workspace and session must be resolved before run creation")

        return await self.run_service.create_run(
            session_id=context.session.id,
            user_input=context.message,
            status="queued",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
        )

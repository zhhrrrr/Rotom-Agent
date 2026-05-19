from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session as SessionModel
from app.gateway.request_context import RequestContext
from app.services import SessionService


class SessionRouter:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.session_service = SessionService(db)

    async def resolve_session(self, context: RequestContext) -> SessionModel:
        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before session")

        if context.requested_session_id is None:
            return await self.session_service.create_session(
                title=context.message[:50],
                user_id=context.user.id,
                workspace_id=context.workspace.id,
            )

        session = await self.session_service.get_session(context.requested_session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.user_id != context.user.id or session.workspace_id != context.workspace.id:
            raise HTTPException(status_code=403, detail="Session does not belong to user workspace")

        return session

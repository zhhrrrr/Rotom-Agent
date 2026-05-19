from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import User
from app.gateway.request_context import RequestContext
from app.gateway.run_router import RunRouter
from app.gateway.session_router import SessionRouter
from app.queue.producer import publish_run
from app.schemas import ChatRequest, ChatResponse
from app.services import EventLogService, MessageService, WorkspaceService

logger = get_logger(__name__)


class GatewayService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.event_log_service = EventLogService(db)
        self.message_service = MessageService(db)
        self.run_router = RunRouter(db)
        self.session_router = SessionRouter(db)
        self.workspace_service = WorkspaceService(db)

    async def handle_chat(self, current_user: User, request: ChatRequest) -> ChatResponse:
        context = RequestContext(
            user=current_user,
            message=request.message,
            requested_workspace_id=request.workspace_id,
            requested_session_id=request.session_id,
        )

        context.workspace = await self.workspace_service.resolve_workspace(
            user_id=current_user.id,
            workspace_id=request.workspace_id,
        )
        if context.workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

        await self._record_request_received(context)
        await self._record_auth_checked(context)
        await self._record_workspace_resolved(context)

        context.session = await self.session_router.resolve_session(context)
        await self._record_session_resolved(context)

        await self.run_router.ensure_no_active_run(context)

        user_message = await self.message_service.save_user_message(
            session_id=context.session.id,
            content=context.message,
            user_id=context.user.id,
            workspace_id=context.workspace.id,
        )

        context.run = await self.run_router.create_run(context)
        user_message.run_id = context.run.id
        await self.db.commit()

        await self._record_run_created(context)

        await publish_run(context.run.id)
        await self._record_run_queued(context)
        logger.info(
            "Gateway queued run run_id=%s session_id=%s user_id=%s workspace_id=%s",
            context.run.id,
            context.session.id,
            context.user.id,
            context.workspace.id,
        )

        return ChatResponse(
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
            run_id=context.run.id,
            status=context.run.status,
        )

    async def _record_request_received(self, context: RequestContext) -> None:
        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before logging")

        await self.event_log_service.record(
            event_type="chat.request.received",
            message="Chat request received",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            payload={"has_session_id": context.requested_session_id is not None},
        )

    async def _record_auth_checked(self, context: RequestContext) -> None:
        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before logging")

        await self.event_log_service.record(
            event_type="gateway.auth.checked",
            message="Gateway auth checked",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            payload={"mode": "jwt"},
        )

    async def _record_workspace_resolved(self, context: RequestContext) -> None:
        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before logging")

        await self.event_log_service.record(
            event_type="workspace.resolved",
            message="Workspace resolved",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
        )

    async def _record_session_resolved(self, context: RequestContext) -> None:
        if context.workspace is None or context.session is None:
            raise RuntimeError("Workspace and session must be resolved before logging")

        await self.event_log_service.record(
            event_type="session.resolved",
            message="Session resolved",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
        )

    async def _record_run_created(self, context: RequestContext) -> None:
        if context.workspace is None or context.session is None or context.run is None:
            raise RuntimeError("Workspace, session, and run must be resolved before logging")

        await self.event_log_service.record(
            event_type="run.created",
            message="Run created",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
            run_id=context.run.id,
        )

    async def _record_run_queued(self, context: RequestContext) -> None:
        if context.workspace is None or context.session is None or context.run is None:
            raise RuntimeError("Workspace, session, and run must be resolved before logging")

        await self.event_log_service.record(
            event_type="run.queued",
            message="Run queued",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
            run_id=context.run.id,
        )

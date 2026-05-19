from typing import Any

from app.db.models import DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID, EventLog
from app.services.trace_service import TraceService


class EventLogService(TraceService):
    """Backward-compatible wrapper around TraceService.

    Existing Gateway, Worker, and Orchestrator code can keep calling record().
    New code should prefer TraceService.log().
    """

    async def record(
        self,
        event_type: str,
        message: str,
        user_id: str = DEFAULT_USER_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        session_id: str | None = None,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EventLog:
        return await self.log(
            event_type=event_type,
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            message=message,
            payload=payload,
        )

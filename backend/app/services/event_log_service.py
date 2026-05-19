from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID, EventLog


class EventLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
        event = EventLog(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            message=message,
            payload=payload,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

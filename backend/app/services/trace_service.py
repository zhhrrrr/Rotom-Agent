from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID, EventLog


class TraceService:
    """Unified trace writer for event_logs.

    The public API accepts optional ids so callers can log as early as possible.
    The database still needs concrete user/workspace ids, so missing values fall
    back to the seeded default identity.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        event_type: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EventLog:
        event = EventLog(
            user_id=user_id or DEFAULT_USER_ID,
            workspace_id=workspace_id or DEFAULT_WORKSPACE_ID,
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            message=message or event_type,
            payload=payload,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

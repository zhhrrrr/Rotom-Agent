from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Run, Session, User, Workspace


@dataclass
class RequestContext:
    user: User
    message: str
    requested_workspace_id: str | None = None
    requested_session_id: str | None = None
    workspace: Workspace | None = None
    session: Session | None = None
    run: Run | None = None

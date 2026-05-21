from pathlib import Path
from shutil import rmtree

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import EventLog, Message, ModelCall, Run, Session, ToolCall, Workspace
from app.services.run_service import ACTIVE_STATUSES


class WorkspaceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workspace(self, user_id: str, name: str) -> Workspace:
        workspace = Workspace(
            user_id=user_id,
            name=name,
            root_path="",
        )
        self.db.add(workspace)
        await self.db.flush()

        workspace.root_path = str(self.workspace_path(user_id, workspace.id))
        await self.ensure_workspace_path(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def create_default_workspace(self, user_id: str) -> Workspace:
        existing_workspace = await self.get_default_workspace(user_id)
        if existing_workspace is not None:
            await self.ensure_workspace_path(existing_workspace)
            return existing_workspace

        workspace = Workspace(
            user_id=user_id,
            name="Default Workspace",
            root_path=str(self.default_workspace_path(user_id)),
        )
        self.db.add(workspace)
        await self.ensure_workspace_path(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def list_workspaces(self, user_id: str) -> list[Workspace]:
        result = await self.db.execute(
            select(Workspace)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_default_workspace(self, user_id: str) -> Workspace | None:
        result = await self.db.execute(
            select(Workspace)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_owned_workspace(self, user_id: str, workspace_id: str) -> Workspace | None:
        result = await self.db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def resolve_workspace(
        self,
        user_id: str,
        workspace_id: str | None = None,
    ) -> Workspace | None:
        if workspace_id is None:
            workspace = await self.get_default_workspace(user_id)
            if workspace is None:
                workspace = await self.create_default_workspace(user_id)
            else:
                await self.ensure_workspace_path(workspace)
            return workspace

        workspace = await self.get_owned_workspace(user_id, workspace_id)
        if workspace is None:
            return None

        await self.ensure_workspace_path(workspace)
        return workspace

    async def has_active_run(self, workspace_id: str) -> bool:
        result = await self.db.execute(
            select(Run.id)
            .where(Run.workspace_id == workspace_id, Run.status.in_(ACTIVE_STATUSES))
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def is_default_workspace(self, workspace: Workspace) -> bool:
        default_workspace = await self.get_default_workspace(workspace.user_id)
        return default_workspace is not None and default_workspace.id == workspace.id

    async def delete_owned_workspace(self, user_id: str, workspace_id: str) -> bool:
        workspace = await self.get_owned_workspace(user_id, workspace_id)
        if workspace is None:
            return False

        if await self.is_default_workspace(workspace):
            raise ValueError("Default Workspace cannot be deleted")

        if await self.has_active_run(workspace_id):
            raise ValueError("Cannot delete a workspace with active runs")

        workspace_root = self.safe_workspace_root(workspace.root_path)
        await self.db.execute(delete(EventLog).where(EventLog.workspace_id == workspace_id))
        await self.db.execute(delete(ToolCall).where(ToolCall.workspace_id == workspace_id))
        await self.db.execute(delete(ModelCall).where(ModelCall.workspace_id == workspace_id))
        await self.db.execute(delete(Message).where(Message.workspace_id == workspace_id))
        await self.db.execute(delete(Run).where(Run.workspace_id == workspace_id))
        await self.db.execute(delete(Session).where(Session.workspace_id == workspace_id))
        await self.db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        await self.db.commit()
        rmtree(workspace_root, ignore_errors=True)
        return True

    async def ensure_workspace_path(self, workspace: Workspace) -> None:
        root_path = self.safe_workspace_root(workspace.root_path)
        root_path.mkdir(parents=True, exist_ok=True)

    def default_workspace_path(self, user_id: str) -> Path:
        return settings.workspace_root / user_id / "default"

    def workspace_path(self, user_id: str, workspace_id: str) -> Path:
        return settings.workspace_root / user_id / workspace_id

    def safe_workspace_root(self, root_path: str) -> Path:
        configured_root = settings.workspace_root.resolve()
        workspace_root = Path(root_path).resolve()
        try:
            workspace_root.relative_to(configured_root)
        except ValueError as exc:
            raise ValueError("Workspace root_path escapes WORKSPACE_ROOT") from exc
        return workspace_root

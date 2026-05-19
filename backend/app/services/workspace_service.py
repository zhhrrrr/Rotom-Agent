from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Workspace


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

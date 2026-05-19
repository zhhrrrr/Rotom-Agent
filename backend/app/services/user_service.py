from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User, Workspace


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user(self, user_id: str) -> User | None:
        return await self.db.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == self.normalize_email(email))
        )
        return result.scalars().first()

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        display_name: str,
    ) -> User:
        user = User(
            email=self.normalize_email(email),
            hashed_password=hashed_password,
            display_name=display_name,
            status="active",
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_default_workspace(self, user: User) -> Workspace:
        root_path = self.default_workspace_path(user.id)
        root_path.mkdir(parents=True, exist_ok=True)

        workspace = Workspace(
            user_id=user.id,
            name="Default Workspace",
            root_path=str(root_path),
        )
        self.db.add(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def get_default_workspace(self, user_id: str) -> Workspace | None:
        result = await self.db.execute(
            select(Workspace)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return await self.db.get(Workspace, workspace_id)

    async def resolve_workspace(
        self,
        user: User,
        workspace_id: str | None = None,
    ) -> Workspace | None:
        if workspace_id is None:
            workspace = await self.get_default_workspace(user.id)
            if workspace is not None:
                return workspace
            return await self.create_default_workspace(user)

        workspace = await self.get_workspace(workspace_id)
        if workspace is None or workspace.user_id != user.id:
            return None
        return workspace

    def default_workspace_path(self, user_id: str) -> Path:
        return settings.workspace_root / user_id / "default"

    def normalize_email(self, email: str) -> str:
        return email.strip().lower()

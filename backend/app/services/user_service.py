from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


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

    def normalize_email(self, email: str) -> str:
        return email.strip().lower()

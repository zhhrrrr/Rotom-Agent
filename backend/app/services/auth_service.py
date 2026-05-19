from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User, Workspace
from app.services.user_service import UserService
from app.services.workspace_service import WorkspaceService


class AuthError(Exception):
    pass


class EmailAlreadyRegisteredError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_service = UserService(db)
        self.workspace_service = WorkspaceService(db)

    async def register(
        self,
        email: str,
        password: str,
        display_name: str,
    ) -> tuple[User, Workspace, str]:
        existing_user = await self.user_service.get_user_by_email(email)
        if existing_user is not None:
            raise EmailAlreadyRegisteredError("Email already registered")

        user = await self.user_service.create_user(
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
        )
        workspace = await self.workspace_service.create_default_workspace(user.id)
        token = create_access_token(subject=user.id)
        return user, workspace, token

    async def login(self, email: str, password: str) -> str:
        user = await self.user_service.get_user_by_email(email)
        if user is None or user.status != "active":
            raise InvalidCredentialsError("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Invalid email or password")

        return create_access_token(subject=user.id)

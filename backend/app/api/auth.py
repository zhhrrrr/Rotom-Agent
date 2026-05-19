from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import get_session
from app.db.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    WorkspaceService,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    try:
        _user, _workspace, token = await AuthService(db).register(
            email=request.email,
            password=request.password,
            display_name=request.display_name,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    try:
        token = await AuthService(db).login(
            email=request.email,
            password=request.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    workspace = await WorkspaceService(db).get_default_workspace(current_user.id)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        status=current_user.status,
        default_workspace_id=workspace.id if workspace else None,
    )

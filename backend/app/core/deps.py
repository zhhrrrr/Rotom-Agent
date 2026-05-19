from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.database import get_session
from app.db.models import User
from app.services import UserService


# 定义一个 Bearer Token 认证方案
# 它会从请求头中读取：
# Authorization: Bearer <token>
#
# auto_error=True 表示：
# 如果请求没有带 Authorization 头，FastAPI 会自动返回 403/401 类错误
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    # 从请求头中提取 Bearer Token
    # credentials 类型是 HTTPAuthorizationCredentials
    #
    # credentials.scheme 一般是 "Bearer"
    # credentials.credentials 才是真正的 token 字符串
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],

    # 通过 FastAPI 依赖注入获取数据库 AsyncSession
    # get_session 一般是一个 async generator，负责创建和关闭数据库会话
    db: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    # 统一定义认证失败异常
    # 后面 token 解析失败、用户不存在、用户被禁用，都返回这个异常
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 解码 access token
        # credentials.credentials 是 Bearer 后面的 token 字符串
        #
        # 例如请求头：
        # Authorization: Bearer eyJhbGciOi...
        #
        # 那么 credentials.credentials 就是：
        # eyJhbGciOi...
        payload = decode_access_token(credentials.credentials)

    except ValueError as exc:
        # 如果 token 过期、签名错误、格式错误，就抛出 401
        raise credentials_exception from exc

    # 从 JWT payload 里取 sub 字段
    # sub 通常表示 subject，也就是当前 token 对应的用户 ID
    user_id = payload.get("sub")

    # 校验 user_id 必须是非空字符串
    # 如果 token 里没有 sub，或者 sub 格式不对，也认为认证失败
    if not isinstance(user_id, str) or not user_id:
        raise credentials_exception

    # 根据 user_id 查询数据库里的用户
    user = await UserService(db).get_user(user_id)

    # 如果用户不存在，或者用户状态不是 active，则认证失败
    if user is None or user.status != "active":
        raise credentials_exception

    # 返回当前登录用户
    # 后续接口就可以直接拿到 current_user
    return user
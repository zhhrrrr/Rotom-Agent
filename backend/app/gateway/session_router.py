from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session as SessionModel
from app.gateway.request_context import RequestContext
from app.services import SessionService
from app.services.session_service import DEFAULT_SESSION_TITLE


class SessionRouter:
    """负责把一次 chat 请求路由到正确的 Session。

    GatewayService 只关心“我要一个可用的 session”。
    具体是创建新 session，还是校验并复用旧 session，都放在这里。
    这样 chat.py 和 GatewayService 不会堆满 session 细节。
    """

    def __init__(self, db: AsyncSession) -> None:
        # db 是当前 HTTP 请求里的数据库会话。
        # SessionRouter 不自己创建连接，保证它和 GatewayService 其他步骤处在同一个请求上下文。
        self.db = db
        self.session_service = SessionService(db)

    async def resolve_session(self, context: RequestContext) -> SessionModel:
        """根据 RequestContext 创建或复用 Session。

        v1 的 Session 必须绑定 workspace。
        所以调用本方法前，GatewayService 必须先完成 workspace 解析。
        """

        if context.workspace is None:
            # 这是开发期保护：说明 Gateway 编排顺序写错了。
            # 用户请求不应该直接触发这个错误；正常情况下 workspace 早已解析完成。
            raise RuntimeError("Workspace must be resolved before session")

        if context.requested_session_id is None:
            # 没传 session_id：代表用户开启新对话。
            # title 暂时截取用户消息前 50 个字符，后续可以换成模型总结标题。
            return await self.session_service.create_session(
                user_id=context.user.id,
                workspace_id=context.workspace.id,
                title=context.message[:50],
            )

        # 传了 session_id：代表用户想继续某个旧对话。
        # v1 不能只按 session_id 查，必须同时带上当前 user 和 workspace 做归属校验。
        session = await self.session_service.get_owned_session(
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.requested_session_id,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.title == DEFAULT_SESSION_TITLE:
            session.title = self.session_service.normalize_title(context.message)

        # 走到这里，说明这个 session 可以安全复用。
        return session

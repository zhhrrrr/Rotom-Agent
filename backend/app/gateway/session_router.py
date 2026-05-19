from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session as SessionModel
from app.gateway.request_context import RequestContext
from app.services import SessionService


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
                title=context.message[:50],
                user_id=context.user.id,
                workspace_id=context.workspace.id,
            )

        # 传了 session_id：代表用户想继续某个旧对话。
        # 先按主键查 session 是否存在。
        session = await self.session_service.get_session(context.requested_session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # 关键安全检查：
        # session 必须同时属于当前用户和当前 workspace。
        # 这样用户不能拿别人的 session_id 继续对话，也不能把 A workspace 的 session
        # 错接到 B workspace 里执行工具。
        if session.user_id != context.user.id or session.workspace_id != context.workspace.id:
            raise HTTPException(status_code=403, detail="Session does not belong to user workspace")

        # 走到这里，说明这个 session 可以安全复用。
        return session

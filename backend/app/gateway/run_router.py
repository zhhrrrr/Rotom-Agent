from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run
from app.gateway.request_context import RequestContext
from app.services import RunService


class RunRouter:
    """负责一次 Agent Run 的路由与创建。

    Session 表示一段对话，Run 表示这段对话里某一次具体执行。
    例如用户连续发三条消息，通常会有一个 session 和三个 run。
    """

    def __init__(self, db: AsyncSession) -> None:
        # 复用 GatewayService 传入的数据库会话。
        # 这样 active run 检查和 run 创建可以和同一次请求里的其他数据库操作自然衔接。
        self.db = db
        self.run_service = RunService(db)

    async def ensure_no_active_run(self, context: RequestContext) -> None:
        """限制同一个 session 同时只能有一个活跃 run。

        如果同一段对话同时跑多个 queued/running run，模型上下文和消息顺序会变得不稳定。
        第一版先用这个规则保证行为可预测；后续要支持并行时，再设计更明确的队列策略。
        """

        if context.session is None:
            # 开发期保护：active run 检查必须发生在 session 解析之后。
            raise RuntimeError("Session must be resolved before active run check")

        active_run = await self.run_service.get_active_run(context.session.id)
        if active_run is not None:
            # 409 表示请求和当前资源状态冲突。
            # 这里的冲突是：这个 session 已经有任务正在排队或执行。
            raise HTTPException(
                status_code=409,
                detail="current session already has a running run",
            )

    async def create_run(self, context: RequestContext) -> Run:
        """创建 queued run。

        Run 必须绑定 user、workspace、session。
        Worker 后续只拿到 run_id，就能回数据库找出它属于谁、在哪个 workspace 执行。
        """

        if context.workspace is None or context.session is None:
            # 开发期保护：run 创建必须在 workspace 和 session 都确定之后。
            raise RuntimeError("Workspace and session must be resolved before run creation")

        return await self.run_service.create_run(
            session_id=context.session.id,
            user_input=context.message,
            status="queued",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
        )

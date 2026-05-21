from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import User
from app.gateway.request_context import RequestContext
from app.gateway.run_router import RunRouter
from app.gateway.session_router import SessionRouter
from app.queue.producer import publish_run
from app.schemas import ChatRequest, ChatResponse
from app.services import MessageService, TraceService, WorkspaceService
from app.streaming.run_stream import prepare_run_stream


# 创建当前模块的 logger
# __name__ 表示当前 Python 模块名，方便日志里定位来源
logger = get_logger(__name__)


class GatewayService:
    """
    GatewayService 是 Chat 请求的入口编排服务。

    它不直接执行 Agent。
    它主要负责：
    1. 解析用户请求上下文；
    2. 解析 workspace；
    3. 解析或创建 session；
    4. 检查同一个 session 下是否已有正在运行的 run；
    5. 保存用户消息；
    6. 创建 queued run；
    7. 把 run_id 投递到 RabbitMQ；
    8. 返回 queued 响应。
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        构造函数。

        参数：
            db: 当前请求对应的异步数据库会话 AsyncSession。

        这里把多个 service/router 都初始化好。
        它们共用同一个 db session，保证一次请求中的数据库操作可以统一 commit。
        """

        # 保存当前请求的数据库 session
        self.db = db

        # Trace 服务：统一负责写 event_logs 表
        self.trace_service = TraceService(db)

        # 消息服务：负责写 messages 表
        self.message_service = MessageService(db)

        # Run 路由器：负责检查 active run、创建 run
        self.run_router = RunRouter(db)

        # Session 路由器：负责解析已有 session 或创建新 session
        self.session_router = SessionRouter(db)

        # Workspace 服务：负责解析当前用户可以访问的 workspace
        self.workspace_service = WorkspaceService(db)

    async def handle_chat(self, current_user: User, request: ChatRequest) -> ChatResponse:
        """
        处理一次用户 chat 请求。

        输入：
            current_user: 已经通过 JWT 鉴权得到的当前用户
            request: 前端传来的 ChatRequest，包括 message、workspace_id、session_id 等

        输出：
            ChatResponse，包含 user_id、workspace_id、session_id、run_id、status

        核心流程：
            1. 构造 RequestContext；
            2. 解析 workspace；
            3. 记录请求入口事件；
            4. 解析 session；
            5. 检查当前 session 是否已有 queued/running run；
            6. 保存 user message；
            7. 创建 queued run；
            8. 提交数据库事务；
            9. 发布 run_id 到 RabbitMQ；
            10. 返回 queued 响应。
        """

        # 构造请求上下文对象
        # RequestContext 用来在 Gateway 流程中传递 user、message、workspace、session、run 等状态
        context = RequestContext(
            user=current_user,
            message=request.message,
            requested_workspace_id=request.workspace_id,
            requested_session_id=request.session_id,
        )

        # 解析 workspace
        # 如果 request.workspace_id 有值，就尝试解析指定 workspace
        # 如果没有，WorkspaceService 可能会返回默认 workspace
        context.workspace = await self.workspace_service.resolve_workspace(
            user_id=current_user.id,
            workspace_id=request.workspace_id,
        )

        # 如果 workspace 不存在，直接返回 404
        # 这一步也可以理解为 workspace 访问校验的一部分
        if context.workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # 记录：收到 chat 请求
        await self._record_request_received(context)

        # 记录：网关鉴权已完成
        # 注意：真正的 JWT 鉴权通常在 API dependency 里已经完成了
        # 这里记录的是一个事件日志，用于 trace
        await self._record_auth_checked(context)

        # 记录：workspace 已解析
        await self._record_workspace_resolved(context)

        # 解析 session
        # 如果请求里带 session_id，就查询这个 session
        # 如果没有 session_id，就创建新 session
        context.session = await self.session_router.resolve_session(context)

        # 记录：session 已解析
        await self._record_session_resolved(context)

        # 检查同一个 session 下是否已经有 queued/running 的 run
        # 目的：防止同一个会话同时跑多个 Agent 任务，造成上下文竞争或消息顺序混乱
        await self.run_router.ensure_no_active_run(context)

        # 保存用户消息到 messages 表
        # 此时 run 还没创建，所以这里可能暂时没有 run_id
        user_message = await self.message_service.save_user_message(
            session_id=context.session.id,
            content=context.message,
            user_id=context.user.id,
            workspace_id=context.workspace.id,
        )

        # 创建 Run
        # 一般状态是 queued
        # 真正执行由 Worker 消费 RabbitMQ 后完成
        context.run = await self.run_router.create_run(context)

        # 把刚才保存的 user_message 绑定到当前 run
        # 如果 user_message 是 SQLAlchemy ORM 对象，并且仍在当前 session 里，
        # 这次赋值会被数据库 session 追踪，commit 时会更新到数据库
        user_message.run_id = context.run.id

        # 提交数据库事务
        # 到这里，user message 和 run 都应该已经入库
        await self.db.commit()

        # 记录：run 已创建
        await self._record_run_created(context)

        # 把 run_id 发布到 RabbitMQ
        # 注意只发布 run_id，不发布完整上下文
        # Worker 收到 run_id 后，再从数据库加载 run/session/messages
        await prepare_run_stream(context.run.id)
        await publish_run(context.run.id)

        # 记录：run 已入队
        await self._record_run_queued(context)

        # 打印结构化日志，方便 docker logs 排查
        logger.info(
            "Gateway queued run run_id=%s session_id=%s user_id=%s workspace_id=%s",
            context.run.id,
            context.session.id,
            context.user.id,
            context.workspace.id,
        )

        # 立即返回给前端
        # 注意：这里并不返回最终回答，只返回 queued 状态
        # 前端后续应该轮询 GET /api/runs/{run_id} 或用 WebSocket/SSE 获取结果
        return ChatResponse(
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
            run_id=context.run.id,
            status=context.run.status,
        )

    async def _record_request_received(self, context: RequestContext) -> None:
        """
        记录 chat.request.received 事件。

        这个事件表示：
            API/Gateway 已经收到了用户 chat 请求。

        payload 中的 has_session_id 用来区分：
            用户是在已有 session 里继续对话，
            还是新建一个 session。
        """

        # 这里要求 workspace 必须已经解析完成
        # 因为 event_logs 需要 workspace_id 做隔离和查询
        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before logging")

        await self.trace_service.log(
            event_type="chat.request.received",
            message="Chat request received",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            payload={"has_session_id": context.requested_session_id is not None},
        )

    async def _record_auth_checked(self, context: RequestContext) -> None:
        """
        记录 gateway.auth.checked 事件。

        这个事件表示：
            当前请求已经完成鉴权检查。

        注意：
            真正的 JWT 校验通常发生在 FastAPI dependency 中。
            这里记录的是 trace 事件，不是重新鉴权。
        """

        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before logging")

        await self.trace_service.log(
            event_type="gateway.auth.checked",
            message="Gateway auth checked",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            payload={"mode": "jwt"},
        )

    async def _record_workspace_resolved(self, context: RequestContext) -> None:
        """
        记录 workspace.resolved 事件。

        这个事件表示：
            Gateway 已经确认当前请求属于哪个 workspace。
        """

        if context.workspace is None:
            raise RuntimeError("Workspace must be resolved before logging")

        await self.trace_service.log(
            event_type="workspace.resolved",
            message="Workspace resolved",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
        )

    async def _record_session_resolved(self, context: RequestContext) -> None:
        """
        记录 session.resolved 事件。

        这个事件表示：
            当前请求对应的 session 已经确定。

        可能是：
            1. 查询到了已有 session；
            2. 创建了新的 session。
        """

        if context.workspace is None or context.session is None:
            raise RuntimeError("Workspace and session must be resolved before logging")

        await self.trace_service.log(
            event_type="session.resolved",
            message="Session resolved",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
        )

    async def _record_run_created(self, context: RequestContext) -> None:
        """
        记录 run.created 事件。

        这个事件表示：
            runs 表里已经创建了一条新的 Run 记录。
        """

        if context.workspace is None or context.session is None or context.run is None:
            raise RuntimeError("Workspace, session, and run must be resolved before logging")

        await self.trace_service.log(
            event_type="run.created",
            message="Run created",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
            run_id=context.run.id,
        )

    async def _record_run_queued(self, context: RequestContext) -> None:
        """
        记录 run.queued 事件。

        这个事件表示：
            run_id 已经发布到 RabbitMQ 队列中，
            等待 Worker 消费执行。
        """

        if context.workspace is None or context.session is None or context.run is None:
            raise RuntimeError("Workspace, session, and run must be resolved before logging")

        await self.trace_service.log(
            event_type="run.queued",
            message="Run queued",
            user_id=context.user.id,
            workspace_id=context.workspace.id,
            session_id=context.session.id,
            run_id=context.run.id,
        )

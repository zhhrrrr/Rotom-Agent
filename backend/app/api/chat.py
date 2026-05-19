from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.db.database import get_session
from app.db.models import Message, User
from app.queue.producer import publish_run
from app.services import EventLogService, MessageService, RunService, SessionService, WorkspaceService


# APIRouter 是 FastAPI 的“路由分组”。
# prefix="/api" 表示这个文件里的接口都会以 /api 开头。
# tags=["chat"] 会让 Swagger 文档里把这些接口归到 chat 分组。
router = APIRouter(prefix="/api", tags=["chat"])
logger = get_logger(__name__)


# Pydantic 模型用于描述请求体。
# FastAPI 会自动用它校验 JSON 请求，并生成 Swagger 文档。
class ChatRequest(BaseModel):
    # Field(min_length=1) 表示 message 不能为空字符串。
    message: str = Field(min_length=1)
    # session_id 可选：不传就创建新会话；传了就继续已有会话。
    session_id: str | None = None
    workspace_id: str | None = None


# 响应模型用于规定接口返回给前端/调用方的 JSON 结构。
class ChatResponse(BaseModel):
    user_id: str
    workspace_id: str
    session_id: str
    run_id: str
    status: str


class RunResponse(BaseModel):
    run_id: str
    user_id: str
    workspace_id: str
    session_id: str
    status: str
    error: str | None
    answer: str | None


# POST /api/chat
# 当前只做“入队”阶段：
# 1. 创建或加载 session
# 2. 创建 queued run
# 3. 保存 user message
# 4. 把 run_id 发到 RabbitMQ
# 真正执行 Agent 的逻辑后续由 Worker 消费 RabbitMQ 后完成。
@router.post("/chat", response_model=ChatResponse)
async def create_chat_run(
    request: ChatRequest,
    # Depends(get_session) 是 FastAPI 的依赖注入。
    # 每次请求进来时，FastAPI 会调用 get_session() 创建 AsyncSession，
    # 然后把 db 传进这个函数；请求结束后 session 会自动关闭。
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChatResponse:
    # Service 层封装数据库操作，API 层只编排业务流程。
    session_service = SessionService(db)
    message_service = MessageService(db)
    run_service = RunService(db)
    workspace_service = WorkspaceService(db)
    event_log_service = EventLogService(db)

    workspace = await workspace_service.resolve_workspace(
        user_id=current_user.id,
        workspace_id=request.workspace_id,
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    await event_log_service.record(
        event_type="chat.request.received",
        message="Chat request received",
        user_id=current_user.id,
        workspace_id=workspace.id,
        payload={"has_session_id": request.session_id is not None},
    )
    await event_log_service.record(
        event_type="gateway.auth.checked",
        message="Gateway auth checked",
        user_id=current_user.id,
        workspace_id=workspace.id,
        payload={"mode": "jwt"},
    )
    await event_log_service.record(
        event_type="workspace.resolved",
        message="Workspace resolved",
        user_id=current_user.id,
        workspace_id=workspace.id,
    )

    if request.session_id is None:
        # 没传 session_id，说明这是一个新会话。
        # title 暂时用用户消息前 50 个字符，后续可以让模型总结标题。
        session = await session_service.create_session(
            title=request.message[:50],
            user_id=current_user.id,
            workspace_id=workspace.id,
        )
    else:
        # 传了 session_id，就先确认这个会话确实存在。
        session = await session_service.get_session(request.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.user_id != current_user.id or session.workspace_id != workspace.id:
            raise HTTPException(status_code=403, detail="Session does not belong to user workspace")
    await event_log_service.record(
        event_type="session.resolved",
        message="Session resolved",
        user_id=current_user.id,
        workspace_id=workspace.id,
        session_id=session.id,
    )

    # 并发控制：同一个 Session 同一时间只允许一个 queued/running Run。
    # 全局并发交给 Worker 数量和 RabbitMQ prefetch_count 控制。
    active_run = await run_service.get_active_run(session.id)
    if active_run is not None:
        raise HTTPException(
            status_code=409,
            detail="current session already has a running run",
        )

    # 每次用户提交消息，都创建一个新的 Run。
    # queued 表示任务已入库，等待 Worker 消费 RabbitMQ 后执行。
    run = await run_service.create_run(
        session_id=session.id,
        user_input=request.message,
        status="queued",
        user_id=current_user.id,
        workspace_id=workspace.id,
    )
    await event_log_service.record(
        event_type="run.created",
        message="Run created",
        user_id=current_user.id,
        workspace_id=workspace.id,
        session_id=session.id,
        run_id=run.id,
    )
    logger.info("API created run run_id=%s session_id=%s", run.id, session.id)
    # 保存 user message 到 PostgreSQL。
    # RabbitMQ 只传 run_id；Worker 之后会用 run_id 回数据库查完整上下文。
    await message_service.save_user_message(
        session_id=session.id,
        run_id=run.id,
        content=request.message,
        user_id=current_user.id,
        workspace_id=workspace.id,
    )
    # 把 run_id 投递到 RabbitMQ，让 Worker 后台异步执行。
    await publish_run(run.id)
    await event_log_service.record(
        event_type="run.queued",
        message="Run queued",
        user_id=current_user.id,
        workspace_id=workspace.id,
        session_id=session.id,
        run_id=run.id,
    )
    logger.info("API queued run run_id=%s session_id=%s", run.id, session.id)

    # 立即返回 queued，不等待模型执行。
    # 这样 HTTP 请求不会被长时间阻塞。
    return ChatResponse(
        user_id=current_user.id,
        workspace_id=workspace.id,
        session_id=session.id,
        run_id=run.id,
        status=run.status,
    )

    '''
    接收用户聊天请求 → 
    创建/复用 Session → 
    创建 Run → 
    保存用户消息 → 
    投递 RabbitMQ → 
    立即返回 queued 状态。
    '''


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run_result(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunResponse:
    run_service = RunService(db)
    run = await run_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    # 最终回答保存在 messages 表，role=assistant，且属于当前 run_id。
    # 如果 Worker 还没跑完，这里会返回 answer=None，status 可能还是 queued/running。
    result = await db.execute(
        select(Message)
        .where(Message.run_id == run_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    assistant_message = result.scalars().first()

    return RunResponse(
        run_id=run.id,
        user_id=run.user_id,
        workspace_id=run.workspace_id,
        session_id=run.session_id,
        status=run.status,
        error=run.error,
        answer=assistant_message.content if assistant_message else None,
    )

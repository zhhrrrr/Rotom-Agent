from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import get_session
from app.db.models import Message, User
from app.gateway import GatewayService
from app.schemas import ChatRequest, ChatResponse, RunResponse
from app.services import RunService


# APIRouter 是 FastAPI 的“路由分组”。
# prefix="/api" 表示这个文件里的接口都会以 /api 开头。
# tags=["chat"] 会让 Swagger 文档里把这些接口归到 chat 分组。
router = APIRouter(prefix="/api", tags=["chat"])


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
    gateway = GatewayService(db)
    return await gateway.handle_chat(current_user, request)


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

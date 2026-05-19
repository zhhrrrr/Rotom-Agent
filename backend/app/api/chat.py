from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import get_session
from app.db.models import EventLog, Message, ModelCall, Run, ToolCall, User
from app.gateway import GatewayService
from app.schemas import ChatRequest, ChatResponse, RunDebugResponse
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


@router.get("/runs/{run_id}", response_model=RunDebugResponse)
async def get_run_result(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunDebugResponse:
    run_service = RunService(db)
    run = await run_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    messages = await _list_by_run(db, Message, run_id)
    tool_calls = await _list_by_run(db, ToolCall, run_id)
    model_calls = await _list_by_run(db, ModelCall, run_id)
    event_logs = await _list_by_run(db, EventLog, run_id)

    return RunDebugResponse(
        run=_serialize_run(run),
        messages=[_serialize_message(message) for message in messages],
        tool_calls=[_serialize_tool_call(tool_call) for tool_call in tool_calls],
        model_calls=[_serialize_model_call(model_call) for model_call in model_calls],
        event_logs=[_serialize_event_log(event_log) for event_log in event_logs],
    )


async def _list_by_run(
    db: AsyncSession,
    model: type[Message] | type[ToolCall] | type[ModelCall] | type[EventLog],
    run_id: str,
) -> list:
    result = await db.execute(
        select(model).where(model.run_id == run_id).order_by(model.created_at.asc())
    )
    return list(result.scalars().all())


def _serialize_run(run: Run) -> dict:
    return {
        "id": run.id,
        "user_id": run.user_id,
        "workspace_id": run.workspace_id,
        "session_id": run.session_id,
        "user_input": run.user_input,
        "status": run.status,
        "current_step": run.current_step,
        "retry_count": run.retry_count,
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _serialize_message(message: Message) -> dict:
    return {
        "id": message.id,
        "user_id": message.user_id,
        "workspace_id": message.workspace_id,
        "session_id": message.session_id,
        "run_id": message.run_id,
        "role": message.role,
        "content": message.content,
        "meta": message.meta,
        "created_at": message.created_at,
    }


def _serialize_tool_call(tool_call: ToolCall) -> dict:
    return {
        "id": tool_call.id,
        "user_id": tool_call.user_id,
        "workspace_id": tool_call.workspace_id,
        "run_id": tool_call.run_id,
        "tool_name": tool_call.tool_name,
        "tool_args": tool_call.tool_args,
        "tool_result": tool_call.tool_result,
        "status": tool_call.status,
        "runtime_type": tool_call.runtime_type,
        "risk_level": tool_call.risk_level,
        "error": tool_call.error,
        "created_at": tool_call.created_at,
        "finished_at": tool_call.finished_at,
    }


def _serialize_model_call(model_call: ModelCall) -> dict:
    return {
        "id": model_call.id,
        "user_id": model_call.user_id,
        "workspace_id": model_call.workspace_id,
        "session_id": model_call.session_id,
        "run_id": model_call.run_id,
        "provider": model_call.provider,
        "model": model_call.model,
        "request_messages": model_call.request_messages,
        "request_tools": model_call.request_tools,
        "response_message": model_call.response_message,
        "prompt_tokens": model_call.prompt_tokens,
        "completion_tokens": model_call.completion_tokens,
        "latency_ms": model_call.latency_ms,
        "status": model_call.status,
        "error": model_call.error,
        "created_at": model_call.created_at,
    }


def _serialize_event_log(event_log: EventLog) -> dict:
    return {
        "id": event_log.id,
        "user_id": event_log.user_id,
        "workspace_id": event_log.workspace_id,
        "session_id": event_log.session_id,
        "run_id": event_log.run_id,
        "event_type": event_log.event_type,
        "message": event_log.message,
        "payload": event_log.payload,
        "created_at": event_log.created_at,
    }

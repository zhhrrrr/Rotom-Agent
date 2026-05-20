import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.database import AsyncSessionLocal, get_session
from app.db.models import Run, RunChunk, User
from app.schemas import RunChunkRead
from app.services import ChunkService, RunService

# 一个普通 HTTP 接口用于查询历史 chunks，
# 一个 SSE 流接口用于实时推送 chunks，实现 Agent 流式输出。


'''
用户发起 run
   ↓
Agent 开始执行
   ↓
LLM streaming API 一点一点吐 token
   ↓
后端把 token 聚合成 chunk
   ↓
写入 run_chunks 表
   ↓
SSE 接口轮询 run_chunks 表
   ↓
发现新 chunk
   ↓
yield 给前端
   ↓
前端追加显示
'''

# Run 的终态状态
# 一旦 run 进入这些状态，说明任务已经结束
# SSE 流可以停止推送
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "timeout"}

# SSE 轮询数据库的间隔
# 每 0.5 秒检查一次有没有新的 chunk
SSE_POLL_INTERVAL_SECONDS = 0.5


# 创建 runs 路由组
# 所有接口前缀都是 /api/runs
router = APIRouter(prefix="/api/runs", tags=["runs"])


# 查询某个 run 的历史 chunks
#
# GET /api/runs/{run_id}/chunks
#
# 用途：
# - 页面刷新后恢复历史输出
# - 客户端断线后补拉漏掉的 chunk
# - CMD/Web 客户端做 resume
@router.get("/{run_id}/chunks", response_model=list[RunChunkRead])
async def list_run_chunks(
    run_id: str,

    # 当前请求使用的数据库 session
    db: Annotated[AsyncSession, Depends(get_session)],

    # 当前登录用户
    current_user: Annotated[User, Depends(get_current_user)],

    # 只查询 chunk_index > after 的 chunk
    # 例如 after=10，表示只拿 11 之后的 chunk
    after: Annotated[int | None, Query(ge=-1)] = None,

    # 最多返回多少条 chunk
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[RunChunkRead]:

    # 先检查这个 run 是否属于当前用户
    # 防止用户读取别人的 run
    await _get_owned_run_or_404(db, current_user.id, run_id)

    # 查询 chunks
    chunks = await ChunkService(db).list_chunks(
        run_id=run_id,
        after_index=after,
        limit=limit,
    )

    # 把 ORM 对象转换成 Pydantic 返回模型
    return [_chunk_read(chunk) for chunk in chunks]


# SSE 流式接口
#
# GET /api/runs/{run_id}/stream
#
# 用途：
# - 实时推送 Agent 输出
# - 实现 ChatGPT 那种打字机效果
# - 持续把新的 RunChunk 推给前端
@router.get("/{run_id}/stream")
async def stream_run_chunks(
    run_id: str,

    # 这里的 db 主要用于连接刚开始时做权限校验
    db: Annotated[AsyncSession, Depends(get_session)],

    # 当前登录用户
    current_user: Annotated[User, Depends(get_current_user)],

    # 客户端已经看到的最后一个 chunk_index
    # 服务端只推送 after 之后的新 chunk
    after: Annotated[int | None, Query(ge=-1)] = None,
) -> StreamingResponse:

    # 先检查 run 是否存在，并且是否属于当前用户
    await _get_owned_run_or_404(db, current_user.id, run_id)

    # 返回 StreamingResponse
    # 这会让 HTTP 连接保持打开，不一次性结束
    return StreamingResponse(
        _run_chunk_events(
            run_id=run_id,
            user_id=current_user.id,
            after_index=after,
        ),

        # SSE 必须使用 text/event-stream
        media_type="text/event-stream",

        headers={
            # 禁止缓存，否则流式输出可能被缓存层影响
            "Cache-Control": "no-cache",

            # 保持长连接
            "Connection": "keep-alive",

            # 禁止 Nginx buffering
            # 否则 Nginx 可能攒一批数据才发给前端，导致不实时
            "X-Accel-Buffering": "no",
        },
    )


# 真正生成 SSE 事件流的异步 generator
#
# 它会不断：
# 1. 查询 run 当前状态
# 2. 查询新的 chunks
# 3. yield SSE event 给前端
# 4. 如果 run 结束，则发送 done 并退出
async def _run_chunk_events(
    run_id: str,
    user_id: str,
    after_index: int | None,
) -> AsyncGenerator[str, None]:

    # last_index 表示当前已经推送到哪个 chunk_index
    # 如果客户端没传 after，就从 -1 开始，表示从第一个 chunk 开始推
    last_index = after_index if after_index is not None else -1

    while True:
        # 每轮循环都创建新的 db session
        #
        # 注意：
        # 不复用外层 request 的 db session，
        # 因为 SSE 连接可能持续很久。
        async with AsyncSessionLocal() as db:

            # 查询 run，并验证归属用户
            run = await RunService(db).get_owned_run(
                user_id=user_id,
                run_id=run_id,
            )

            # 如果 run 不存在，推送 error 事件，然后结束流
            if run is None:
                yield _sse_event(
                    "error",
                    {
                        "run_id": run_id,
                        "error": "Run not found",
                    },
                )
                return

            # 查询 last_index 之后的新 chunks
            chunks = await ChunkService(db).list_chunks(
                run_id=run_id,
                after_index=last_index,
            )

            # 把每个 chunk 转成 SSE event 推给前端
            for chunk in chunks:
                # 更新已经推送到的最后 index
                last_index = chunk.chunk_index

                # event 名叫 chunk
                # data 是 chunk 的完整 JSON payload
                yield _sse_event("chunk", _chunk_payload(chunk))

            # 如果 run 已经结束，发送 done 事件，然后关闭 SSE 流
            if run.status in TERMINAL_RUN_STATUSES:
                yield _sse_event(
                    "done",
                    {
                        "run_id": run.id,
                        "status": run.status,
                    },
                )
                return

        # 如果 run 还没结束，就等待 0.5 秒后继续查
        await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)


# 根据 run_id 查询 run，并检查它是否属于当前用户
#
# 如果不存在，直接抛 404
async def _get_owned_run_or_404(
    db: AsyncSession,
    user_id: str,
    run_id: str,
) -> Run:
    run = await RunService(db).get_owned_run(
        user_id=user_id,
        run_id=run_id,
    )

    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return run


# 把数据库里的 RunChunk ORM 对象
# 转换成 API 返回用的 RunChunkRead Pydantic 对象
def _chunk_read(chunk: RunChunk) -> RunChunkRead:
    return RunChunkRead(
        id=chunk.id,
        run_id=chunk.run_id,
        user_id=chunk.user_id,
        workspace_id=chunk.workspace_id,
        session_id=chunk.session_id,
        chunk_index=chunk.chunk_index,
        chunk_type=chunk.chunk_type,
        role=chunk.role,
        content=chunk.content,
        payload=chunk.payload,
        is_final=chunk.is_final,
        created_at=chunk.created_at,
    )


# 把 RunChunk ORM 对象转换成可以 JSON 序列化的 dict
#
# 注意：
# created_at 是 datetime，不能直接 json.dumps
# 所以这里用 isoformat() 转成字符串
def _chunk_payload(chunk: RunChunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "run_id": chunk.run_id,
        "user_id": chunk.user_id,
        "workspace_id": chunk.workspace_id,
        "session_id": chunk.session_id,
        "chunk_index": chunk.chunk_index,
        "chunk_type": chunk.chunk_type,
        "role": chunk.role,
        "content": chunk.content,
        "payload": chunk.payload,
        "is_final": chunk.is_final,
        "created_at": chunk.created_at.isoformat(),
    }


# 构造标准 SSE 文本格式
#
# SSE 格式：
#
# event: 事件名
# data: JSON字符串
#
# 注意最后必须有两个换行 \n\n
# 这表示一个 SSE event 结束
def _sse_event(event: str, data: dict[str, Any]) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )
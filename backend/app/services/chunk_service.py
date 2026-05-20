from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run, RunChunk
from app.schemas import RunChunkCreate


class ChunkService:
    """Persist and read ordered chunks for a run.

    Chunks are append-only in v1.5. Each run has its own zero-based
    chunk_index sequence so web and CMD clients can reconnect and resume from
    the last index they have seen.
    """

    # 初始化 ChunkService
    # db 是当前请求/任务使用的异步数据库会话
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # 基于 Run 对象追加一个 chunk
    # 是 append_chunk 的快捷封装
    #
    # 常用于：
    # - assistant 流式输出
    # - tool call
    # - status 更新
    #
    # 自动从 run 继承：
    # - user_id
    # - workspace_id
    # - session_id
    async def append_run_chunk(
        self,
        run: Run,
        chunk_type: str,
        content: str = "",
        role: str | None = None,
        payload: dict[str, Any] | None = None,
        is_final: bool = False,
    ) -> RunChunk:
        return await self.append_chunk(
            RunChunkCreate(
                run_id=run.id,
                user_id=run.user_id,
                workspace_id=run.workspace_id,
                session_id=run.session_id,
                chunk_type=chunk_type,
                role=role,
                content=content,
                payload=payload,
                is_final=is_final,
            )
        )

    # 真正执行 chunk 写入数据库的方法
    #
    # 流程：
    # 1. 获取当前 run 的下一个 chunk_index
    # 2. 创建 RunChunk ORM 对象
    # 3. 写入数据库
    # 4. commit 提交事务
    # 5. refresh 获取数据库最终状态
    #
    # append-only：
    # chunk 创建后不会修改，只会新增
    async def append_chunk(self, chunk: RunChunkCreate) -> RunChunk:
        next_index = await self._next_chunk_index(chunk.run_id)

        run_chunk = RunChunk(
            run_id=chunk.run_id,
            user_id=chunk.user_id,
            workspace_id=chunk.workspace_id,
            session_id=chunk.session_id,

            # 当前 chunk 在 run 中的顺序
            chunk_index=next_index,

            # chunk 类型
            chunk_type=chunk.chunk_type,

            # assistant / tool / system 等
            role=chunk.role,

            # 给用户展示的文本内容
            content=chunk.content,

            # runtime metadata / tool data
            payload=chunk.payload,

            # 是否为最终 chunk
            is_final=chunk.is_final,
        )

        self.db.add(run_chunk)

        # 提交事务
        await self.db.commit()

        # 从数据库重新加载
        # 获取 created_at / id 等最终值
        await self.db.refresh(run_chunk)

        return run_chunk

    # 查询某个 run 的 chunk 列表
    #
    # 支持：
    # - 增量拉取
    # - reconnect resume
    # - streaming replay
    #
    # after_index:
    # 只返回大于该 index 的 chunk
    #
    # limit:
    # 防止一次返回过多数据
    async def list_chunks(
        self,
        run_id: str,
        after_index: int | None = None,
        limit: int = 500,
    ) -> list[RunChunk]:

        # 限制最大查询数量
        # 防止客户端恶意请求超大分页
        safe_limit = max(1, min(limit, 1000))

        stmt = select(RunChunk).where(RunChunk.run_id == run_id)

        # 增量同步
        # 例如客户端已经拿到 chunk 0~10
        # 这里只拉取 11 之后的
        if after_index is not None:
            stmt = stmt.where(RunChunk.chunk_index > after_index)

        result = await self.db.execute(
            stmt.order_by(RunChunk.chunk_index.asc()).limit(safe_limit)
        )

        # scalars():
        # 提取 ORM 对象
        return list(result.scalars().all())

    # 获取某个 run 的下一个 chunk_index
    #
    # 逻辑：
    # 查询当前 run 最大的 chunk_index
    # 然后 +1
    #
    # 例如：
    # 当前最大 index = 5
    # 返回 6
    #
    # 如果 run 还没有 chunk：
    # 返回 0
    async def _next_chunk_index(self, run_id: str) -> int:
        result = await self.db.execute(
            select(RunChunk.chunk_index)
            .where(RunChunk.run_id == run_id)
            .order_by(RunChunk.chunk_index.desc())
            .limit(1)
        )

        last_index = result.scalars().first()

        # 第一个 chunk
        if last_index is None:
            return 0

        return last_index + 1
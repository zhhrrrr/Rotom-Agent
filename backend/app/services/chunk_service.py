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

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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

    async def append_chunk(self, chunk: RunChunkCreate) -> RunChunk:
        next_index = await self._next_chunk_index(chunk.run_id)
        run_chunk = RunChunk(
            run_id=chunk.run_id,
            user_id=chunk.user_id,
            workspace_id=chunk.workspace_id,
            session_id=chunk.session_id,
            chunk_index=next_index,
            chunk_type=chunk.chunk_type,
            role=chunk.role,
            content=chunk.content,
            payload=chunk.payload,
            is_final=chunk.is_final,
        )
        self.db.add(run_chunk)
        await self.db.commit()
        await self.db.refresh(run_chunk)
        return run_chunk

    async def list_chunks(
        self,
        run_id: str,
        after_index: int | None = None,
        limit: int = 500,
    ) -> list[RunChunk]:
        safe_limit = max(1, min(limit, 1000))
        stmt = select(RunChunk).where(RunChunk.run_id == run_id)
        if after_index is not None:
            stmt = stmt.where(RunChunk.chunk_index > after_index)

        result = await self.db.execute(
            stmt.order_by(RunChunk.chunk_index.asc()).limit(safe_limit)
        )
        return list(result.scalars().all())

    async def _next_chunk_index(self, run_id: str) -> int:
        result = await self.db.execute(
            select(RunChunk.chunk_index)
            .where(RunChunk.run_id == run_id)
            .order_by(RunChunk.chunk_index.desc())
            .limit(1)
        )
        last_index = result.scalars().first()
        if last_index is None:
            return 0
        return last_index + 1

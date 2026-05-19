from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Run

logger = get_logger(__name__)


ACTIVE_STATUSES = {"queued", "running"}

# 这些状态表示一次 Run 已经结束。
# 进入终态时，RunService 会自动写 finished_at。
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


# RunService 负责 runs 表。
# Run 表示一次 Agent 执行任务，例如用户发来一句话后创建一个 queued run。
class RunService:
    def __init__(self, db: AsyncSession) -> None:
        # db 是外部传入的 AsyncSession，不在 Service 里自行创建。
        # 这样 API 和 Worker 都可以用同一套 Service。
        self.db = db

    async def create_run(
        self,
        session_id: str,
        user_input: str,
        status: str = "queued",
    ) -> Run:
        # 新任务默认 queued，表示已经创建但还没被 Worker 执行。
        run = Run(
            session_id=session_id,
            user_input=user_input,
            status=status,
        )
        # add() 加入事务，commit() 写入数据库，refresh() 拿回数据库生成字段。
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_run(self, run_id: str) -> Run | None:
        # 按主键 id 查询 Run。
        return await self.db.get(Run, run_id)

    async def get_active_run(self, session_id: str) -> Run | None:
        # 同一个 Session 第一版只允许一个 queued/running Run。
        # order_by(created_at.asc()) 让返回结果稳定：如果脏数据里有多个，就返回最早的那个。
        result = await self.db.execute(
            select(Run)
            .where(Run.session_id == session_id, Run.status.in_(ACTIVE_STATUSES))
            .order_by(Run.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def update_status(
        self,
        run_id: str,
        status: str,
        error: str | None = None,
    ) -> Run | None:
        # 先查出这条 run。不存在时返回 None，由调用方决定怎么处理。
        run = await self.get_run(run_id)
        if run is None:
            return None

        # 更新状态和错误信息。SQLAlchemy 会追踪这些字段变化。
        old_status = run.status
        run.status = status
        run.error = error

        # 如果进入 completed/failed/cancelled，并且还没结束时间，就记录完成时间。
        if status in TERMINAL_STATUSES and run.finished_at is None:
            run.finished_at = datetime.now(UTC)

        # commit() 时 SQLAlchemy 会生成 UPDATE 语句。
        await self.db.commit()
        await self.db.refresh(run)
        logger.info(
            "Run status change run_id=%s session_id=%s from=%s to=%s error=%s",
            run.id,
            run.session_id,
            old_status,
            status,
            error,
        )
        return run

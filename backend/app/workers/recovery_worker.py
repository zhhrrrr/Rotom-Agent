from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Run
from app.services import RunService, TraceService

logger = get_logger(__name__)


async def recover_stale_running_runs(
    db: AsyncSession,
    stale_after_minutes: int = 30,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=stale_after_minutes)
    result = await db.execute(
        select(Run)
        .where(Run.status == "running", Run.updated_at < cutoff)
        .order_by(Run.updated_at.asc())
    )
    stale_runs = list(result.scalars().all())
    if not stale_runs:
        logger.info("Recovery worker found no stale running runs")
        return 0

    run_service = RunService(db)
    trace_service = TraceService(db)
    error = f"Run timed out after {stale_after_minutes} minutes without worker update"

    for run in stale_runs:
        last_updated_at = run.updated_at
        logger.warning(
            "Recovery worker timeout run_id=%s updated_at=%s",
            run.id,
            last_updated_at,
        )
        await run_service.update_status(
            run.id,
            "timeout",
            error=error,
            current_step="run.timeout",
        )
        await trace_service.log(
            event_type="run.timeout",
            message=error,
            user_id=run.user_id,
            workspace_id=run.workspace_id,
            session_id=run.session_id,
            run_id=run.id,
            payload={
                "stale_after_minutes": stale_after_minutes,
                "cutoff": cutoff.isoformat(),
                "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
            },
        )

    logger.info("Recovery worker timed out stale runs count=%s", len(stale_runs))
    return len(stale_runs)

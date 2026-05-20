from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    EventLog,
    Message,
    ModelCall,
    Run,
    RunChunk,
    Session as SessionModel,
    ToolCall,
)
from app.services.run_service import ACTIVE_STATUSES

DEFAULT_SESSION_TITLE = "New Session"
SESSION_TITLE_MAX_LENGTH = 48


# Service 层负责封装“业务动作”，避免 API 或 Worker 到处直接写数据库操作。
# 这个类专门处理 sessions 表相关的逻辑。
class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        # db 是一次数据库会话，通常由 FastAPI 的 get_session() 注入。
        # Service 不自己创建连接，只使用外部传进来的 session，方便统一管理事务和测试。
        self.db = db

    async def create_session(
        self,
        user_id: str,
        workspace_id: str,
        title: str = DEFAULT_SESSION_TITLE,
    ) -> SessionModel:
        # 创建 ORM 对象。此时它还只在 Python 内存里，没有真正写进数据库。
        session = SessionModel(
            title=title,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        # add() 把对象加入当前数据库会话，等待提交。
        self.db.add(session)
        # commit() 提交事务，真正 INSERT 到数据库。
        await self.db.commit()
        # refresh() 从数据库重新读取一遍，拿到自动生成的 id、created_at 等字段。
        await self.db.refresh(session)
        return session

    def normalize_title(self, title: str) -> str:
        normalized = " ".join(title.strip().split())
        return (normalized[:SESSION_TITLE_MAX_LENGTH] or DEFAULT_SESSION_TITLE)

    async def get_session(self, session_id: str) -> SessionModel | None:
        # db.get(Model, primary_key) 是按主键查询的快捷写法。
        # 查不到时返回 None。
        return await self.db.get(SessionModel, session_id)

    async def get_owned_session(
        self,
        user_id: str,
        workspace_id: str,
        session_id: str,
    ) -> SessionModel | None:
        # v1 不能只按 session_id 查。
        # session_id 本身不是权限证明，必须同时确认它属于当前 user 和 workspace。
        result = await self.db.execute(
            select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
                SessionModel.workspace_id == workspace_id,
            )
        )
        return result.scalars().first()

    async def list_workspace_sessions(
        self,
        user_id: str,
        workspace_id: str,
    ) -> list[SessionModel]:
        result = await self.db.execute(
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.workspace_id == workspace_id,
            )
            .order_by(SessionModel.updated_at.desc(), SessionModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def has_active_run(self, session_id: str) -> bool:
        result = await self.db.execute(
            select(Run.id)
            .where(Run.session_id == session_id, Run.status.in_(ACTIVE_STATUSES))
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def delete_owned_session(
        self,
        user_id: str,
        session_id: str,
    ) -> bool:
        session = await self.get_session(session_id)
        if session is None or session.user_id != user_id:
            return False

        if await self.has_active_run(session_id):
            raise ValueError("Cannot delete a session with active runs")

        run_ids = select(Run.id).where(Run.session_id == session_id)
        await self.db.execute(delete(EventLog).where(EventLog.session_id == session_id))
        await self.db.execute(delete(RunChunk).where(RunChunk.session_id == session_id))
        await self.db.execute(delete(ToolCall).where(ToolCall.run_id.in_(run_ids)))
        await self.db.execute(delete(ModelCall).where(ModelCall.session_id == session_id))
        await self.db.execute(delete(Message).where(Message.session_id == session_id))
        await self.db.execute(delete(Run).where(Run.session_id == session_id))
        await self.db.execute(delete(SessionModel).where(SessionModel.id == session_id))
        await self.db.commit()
        return True

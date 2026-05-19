from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session as SessionModel


# Service 层负责封装“业务动作”，避免 API 或 Worker 到处直接写数据库操作。
# 这个类专门处理 sessions 表相关的逻辑。
class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        # db 是一次数据库会话，通常由 FastAPI 的 get_session() 注入。
        # Service 不自己创建连接，只使用外部传进来的 session，方便统一管理事务和测试。
        self.db = db

    async def create_session(self, title: str = "New Session") -> SessionModel:
        # 创建 ORM 对象。此时它还只在 Python 内存里，没有真正写进数据库。
        session = SessionModel(title=title)
        # add() 把对象加入当前数据库会话，等待提交。
        self.db.add(session)
        # commit() 提交事务，真正 INSERT 到数据库。
        await self.db.commit()
        # refresh() 从数据库重新读取一遍，拿到自动生成的 id、created_at 等字段。
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> SessionModel | None:
        # db.get(Model, primary_key) 是按主键查询的快捷写法。
        # 查不到时返回 None。
        return await self.db.get(SessionModel, session_id)

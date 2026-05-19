from collections.abc import AsyncGenerator

# sqlalchemy让你不用手写大量 SQL，也能用 Python 对象来操作数据库
from sqlalchemy import text 
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.models import Base


# engine 是 SQLAlchemy 连接数据库的入口。
# 这里使用 create_async_engine，因为项目后续的 FastAPI、RabbitMQ、模型调用都会走异步流程。
engine = create_async_engine(
    settings.database_url,
    # 每次从连接池取连接前先检查连接是否还活着，避免数据库重启后拿到坏连接。
    pool_pre_ping=True,
)

# AsyncSessionLocal 是“Session 工厂”，不是一个真正的数据库会话。
# 后续每次请求或 Worker 任务需要访问数据库时，都从这里创建新的 AsyncSession。
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # 提交事务后不自动让 ORM 对象过期，后续读取对象字段时更直观。
    expire_on_commit=False,
)

# 是一个带泛型参数的类型注解。
# AsyncGenerator[每次 yield 出来的类型, 外部 send 进来的类型]
# get_session() 这个函数执行到 yield session 时，会把 session 这个数据库会话对象交给外部使用；等外部用完之后，函数会继续往下执行，完成关闭连接等清理工作。
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    # FastAPI 依赖注入会调用这个函数。
    # yield 前创建 session，接口逻辑执行完后自动退出 async with 并关闭 session。
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    # 先做一次最轻量的 SELECT 1。
    # 如果 DATABASE_URL、账号密码或网络不对，FastAPI 启动时会立刻失败。
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        # 根据 models.py 里的模型定义创建还不存在的表。
        # 这一步不会删除已有表，也不会覆盖已有数据。
        await conn.run_sync(Base.metadata.create_all)

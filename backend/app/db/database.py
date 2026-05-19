from collections.abc import AsyncGenerator

# sqlalchemy让你不用手写大量 SQL，也能用 Python 对象来操作数据库
from sqlalchemy import text 
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.models import Base, DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID


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
        await _upgrade_v1_schema(conn)
        await _seed_default_identity(conn)


async def _upgrade_v1_schema(conn) -> None:
    """Bring a v0 database up to the v1 table shape.

    create_all() will create new tables, but it will not add columns to existing
    tables. These ALTER statements are intentionally additive and idempotent.
    """
    statements = [
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT 'user_default'",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) NOT NULL DEFAULT 'workspace_default'",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT 'user_default'",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) NOT NULL DEFAULT 'workspace_default'",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT 'user_default'",
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) NOT NULL DEFAULT 'workspace_default'",
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS current_step VARCHAR(100)",
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT 'user_default'",
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) NOT NULL DEFAULT 'workspace_default'",
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS runtime_type VARCHAR(32)",
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS risk_level VARCHAR(32)",
        "CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_sessions_workspace_id ON sessions (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_user_id ON messages (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_workspace_id ON messages (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_runs_user_id ON runs (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_runs_workspace_id ON runs (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_tool_calls_user_id ON tool_calls (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_tool_calls_workspace_id ON tool_calls (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_run_chunks_run_id ON run_chunks (run_id)",
        "CREATE INDEX IF NOT EXISTS ix_run_chunks_user_id ON run_chunks (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_run_chunks_workspace_id ON run_chunks (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_run_chunks_session_id ON run_chunks (session_id)",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_run_chunks_run_id_chunk_index "
            "ON run_chunks (run_id, chunk_index)"
        ),
    ]

    for statement in statements:
        await conn.execute(text(statement))


async def _seed_default_identity(conn) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO users (id, email, hashed_password, display_name, status)
            VALUES (:id, :email, :hashed_password, :display_name, :status)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": DEFAULT_USER_ID,
            "email": "default@rotom.local",
            "hashed_password": "not-set",
            "display_name": "Default User",
            "status": "active",
        },
    )
    await conn.execute(
        text(
            """
            INSERT INTO workspaces (id, user_id, name, root_path)
            VALUES (:id, :user_id, :name, :root_path)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": DEFAULT_WORKSPACE_ID,
            "user_id": DEFAULT_USER_ID,
            "name": "Rotom 默认工作区",
            "root_path": str(settings.workspace_root),
        },
    )

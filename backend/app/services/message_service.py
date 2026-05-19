from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID, Message


# MessageService 负责 messages 表。
# 这里把“保存用户消息”“保存助手消息”“查历史消息”封装成方法，
# 后续 /api/chat 和 Worker 都可以复用，不需要重复写 SQLAlchemy 细节。
class MessageService:
    def __init__(self, db: AsyncSession) -> None:
        # 复用外部传入的数据库会话，和其他 Service 可以处在同一个请求/任务上下文里。
        self.db = db

    async def save_user_message(
        self,
        session_id: str,
        content: str,
        run_id: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        meta: dict | None = None,
    ) -> Message:
        # 用户消息固定 role="user"。
        return await self._save_message(
            session_id=session_id,
            run_id=run_id,
            role="user",
            content=content,
            user_id=user_id,
            workspace_id=workspace_id,
            meta=meta,
        )

    async def save_assistant_message(
        self,
        session_id: str,
        content: str,
        run_id: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        meta: dict | None = None,
    ) -> Message:
        # 模型最终回答固定 role="assistant"。
        return await self._save_message(
            session_id=session_id,
            run_id=run_id,
            role="assistant",
            content=content,
            user_id=user_id,
            workspace_id=workspace_id,
            meta=meta,
        )

    async def list_session_messages(self, session_id: str) -> list[Message]:
        # select(Message) 表示查询 messages 表对应的 ORM 对象。
        # where() 添加筛选条件，只拿某个 session 下的消息。
        # order_by() 按创建时间正序，保证历史消息顺序稳定。
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        # scalars() 取出 ORM 对象本身，all() 得到列表。
        return list(result.scalars().all())

    async def _save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        run_id: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        meta: dict | None = None,
    ) -> Message:
        # 私有方法：把 user/assistant 的公共保存逻辑集中到一处。
        # Python 里以下划线开头表示“内部使用”，不是语法强制。
        message = Message(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            role=role,
            content=content,
            meta=meta or {},
        )
        # add -> commit -> refresh 是创建一条 ORM 数据的常见三步。
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

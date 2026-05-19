from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message


DEFAULT_SYSTEM_PROMPT = (
    "你是 Rotom Agent，一个简洁、可靠的智能助手。"
    "你需要根据已有对话上下文回答用户问题。"
    "当用户要求查看目录、读取文件或写入文件时，必须使用可用工具，不要凭空猜测文件内容。"
    "当用户要求执行允许的低风险命令时，必须使用 run_shell 工具。"
)


class ContextBuilder:
    """把数据库里的会话历史拼成模型需要的 messages。

    第一版只做两件事：
    1. 放一条 system prompt。
    2. 读取当前 session 最近 N 条消息。
    """

    def __init__(
        self,
        db: AsyncSession,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        recent_message_limit: int = 20,
    ) -> None:
        # db 是外面传进来的数据库会话，和 Service 的用法一样。
        self.db = db
        # system prompt 是给模型的最高层指令，通常放在 messages 第一条。
        self.system_prompt = system_prompt
        # 默认只取最近 20 条，避免上下文无限变长。
        self.recent_message_limit = recent_message_limit

    async def build(self, session_id: str) -> list[dict[str, str]]:
        # 先取最近 N 条：数据库按 created_at 倒序查，limit 才能真正限制读取数量。
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(self.recent_message_limit)
        )
        recent_messages = list(result.scalars().all())

        # 模型需要从旧到新读上下文，所以把“倒序取出的最近消息”翻回正序。
        recent_messages.reverse()

        model_messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

        # 数据库 Message 对象转成 OpenAI-compatible Chat Completions 的格式。
        for message in recent_messages:
            model_messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        return model_messages

import json
from datetime import UTC, datetime
from typing import Any

from aio_pika import Message
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractRobustChannel,
    AbstractRobustConnection,
    AbstractRobustQueue,
)

from app.db.models import Run
from app.queue.rabbitmq import get_rabbitmq_channel, get_rabbitmq_connection

RUN_STREAM_QUEUE_PREFIX = "rotom_run_stream"
RUN_STREAM_QUEUE_EXPIRES_MS = 10 * 60 * 1000


class RunStreamPublisher:
    """Publish transient run events for live SSE subscribers.

    These events are intentionally not persisted. PostgreSQL remains the source
    of truth for final run state, messages, tool calls, model calls and logs.
    """

    def __init__(
        self,
        connection: AbstractRobustConnection,
        channel: AbstractRobustChannel,
    ) -> None:
        self.connection = connection
        self.channel = channel

    @classmethod
    async def create(cls) -> "RunStreamPublisher":
        connection = await get_rabbitmq_connection()
        channel = await get_rabbitmq_channel(connection)
        return cls(connection, channel)

    async def close(self) -> None:
        await self.connection.close()

    async def publish_run_event(
        self,
        run: Run,
        event_type: str,
        content: str = "",
        role: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.publish(
            run_id=run.id,
            user_id=run.user_id,
            workspace_id=run.workspace_id,
            session_id=run.session_id,
            event_type=event_type,
            content=content,
            role=role,
            payload=payload,
        )

    async def publish(
        self,
        run_id: str,
        event_type: str,
        content: str = "",
        role: str | None = None,
        payload: dict[str, Any] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        body = {
            "run_id": run_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
            "type": event_type,
            "role": role,
            "content": content,
            "payload": payload,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await ensure_run_stream_queue(self.channel, run_id)
        await self.channel.default_exchange.publish(
            Message(
                json.dumps(body, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
            ),
            routing_key=run_stream_queue_name(run_id),
        )


class RunStreamSubscription:
    """Temporary RabbitMQ subscription used by one SSE connection."""

    def __init__(
        self,
        connection: AbstractRobustConnection,
        channel: AbstractRobustChannel,
        queue: AbstractRobustQueue,
    ) -> None:
        self.connection = connection
        self.channel = channel
        self.queue = queue

    @classmethod
    async def create(cls, run_id: str) -> "RunStreamSubscription":
        connection = await get_rabbitmq_connection()
        channel = await get_rabbitmq_channel(connection)
        queue = await ensure_run_stream_queue(channel, run_id)
        return cls(connection, channel, queue)

    async def get(self, timeout: float = 1.0) -> dict[str, Any] | None:
        message = await self.queue.get(timeout=timeout, fail=False)
        if message is None:
            return None

        async with message.process():
            return _decode_message(message)

    async def close(self) -> None:
        await self.queue.delete(if_unused=False, if_empty=False)
        await self.connection.close()


async def ensure_run_stream_queue(
    channel: AbstractRobustChannel,
    run_id: str,
) -> AbstractRobustQueue:
    return await channel.declare_queue(
        run_stream_queue_name(run_id),
        durable=False,
        auto_delete=True,
        arguments={"x-expires": RUN_STREAM_QUEUE_EXPIRES_MS},
    )


async def prepare_run_stream(run_id: str) -> None:
    connection = await get_rabbitmq_connection()
    async with connection:
        channel = await get_rabbitmq_channel(connection)
        await ensure_run_stream_queue(channel, run_id)


def run_stream_queue_name(run_id: str) -> str:
    return f"{RUN_STREAM_QUEUE_PREFIX}.{run_id}"


def _decode_message(message: AbstractIncomingMessage) -> dict[str, Any]:
    return json.loads(message.body.decode("utf-8"))

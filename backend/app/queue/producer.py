import json

from aio_pika import DeliveryMode, Message

from app.core.config import settings
from app.core.logging import get_logger
from app.queue.rabbitmq import (
    declare_run_queue,
    get_rabbitmq_channel,
    get_rabbitmq_connection,
)

logger = get_logger(__name__)


async def publish_run(run_id: str) -> None:
    logger.info("RabbitMQ publish run start run_id=%s", run_id)
    # RabbitMQ 消息体只能是 bytes，所以先把 Python dict 转成 JSON 字符串，再 encode 成 bytes。
    # 这里故意只放 run_id，不放用户输入或 messages。
    # 完整状态保存在 PostgreSQL，RabbitMQ 只负责排队。
    body = json.dumps({"run_id": run_id}).encode("utf-8")

    # 连接 RabbitMQ。这里使用 async with，函数结束时会自动关闭连接。
    connection = await get_rabbitmq_connection()
    async with connection:
        # channel 是实际执行 publish 的通道。
        channel = await get_rabbitmq_channel(connection)
        # 发布前先声明队列，确保 agent_runs 存在。
        queue = await declare_run_queue(channel)

        # Message 是 aio-pika 的消息对象。
        # content_type 标明消息体是 JSON，方便后续 Worker 理解。
        # DeliveryMode.PERSISTENT 表示消息持久化；RabbitMQ 重启后消息尽量保留。
        message = Message(
            body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )

        # default_exchange 是 RabbitMQ 默认交换机。
        # 对默认交换机来说，routing_key 写队列名，就会把消息直接投递到同名队列。
        await channel.default_exchange.publish(
            message,
            routing_key=queue.name,
        )
        logger.info(
            "RabbitMQ publish run end run_id=%s queue=%s",
            run_id,
            queue.name,
        )

import asyncio
import json

from aio_pika.abc import AbstractIncomingMessage

from app.agent import AgentOrchestrator
from app.core.logging import get_logger, setup_logging
from app.db.database import AsyncSessionLocal, init_db
from app.queue.rabbitmq import (
    declare_run_queue,
    get_rabbitmq_channel,
    get_rabbitmq_connection,
)

setup_logging()
logger = get_logger(__name__)


# Worker 是后台消费者，不是 HTTP 服务，所以它不监听端口。
# 它的职责是：
# 1. 主动连接 RabbitMQ
# 2. 等待 agent_runs 队列里的 run_id
# 3. 根据 run_id 去 PostgreSQL 查完整任务状态
# 4. 执行后台任务并更新 run.status


async def handle_message(message: AbstractIncomingMessage) -> None:
    # message.process() 会在代码块成功结束时自动 ack。
    # ack 的意思是告诉 RabbitMQ：“这条消息我处理完了，可以从队列删除。”
    #
    # requeue=False 表示如果这里抛异常，不把消息重新放回队列。
    # 骨架阶段这样可以避免坏消息反复消费造成死循环。
    async with message.process(requeue=False):
        # producer.py 只发送 {"run_id": "..."}。
        # RabbitMQ 只负责排队，不保存完整用户输入和上下文。
        payload = json.loads(message.body.decode("utf-8"))
        run_id = payload["run_id"]
        logger.info("Worker consume run run_id=%s", run_id)

        # Worker 没有 FastAPI 的 Depends(get_session)，所以要手动创建数据库会话。
        async with AsyncSessionLocal() as db:
            orchestrator = AgentOrchestrator(db)
            try:
                result = await orchestrator.run(run_id)
                if result is None:
                    logger.error("Worker run failed or not found run_id=%s", run_id)
                    return

                logger.info("Worker run completed run_id=%s", run_id)
            except Exception:
                logger.exception("Worker exception run_id=%s", run_id)
                raise


async def run_worker() -> None:
    # 启动时先初始化数据库连接和表结构。
    # 如果数据库连不上，Worker 会直接启动失败，方便尽早发现问题。
    await init_db()

    # Worker 主动连接 RabbitMQ，不需要对外暴露端口。
    connection = await get_rabbitmq_connection()
    async with connection:
        channel = await get_rabbitmq_channel(connection)
        # prefetch_count=1 表示一次只拿 1 条未 ack 消息。
        # 这样 Worker 不会一口气拿太多任务，适合第一版串行验证。
        # TODO
        await channel.set_qos(prefetch_count=1)
        # 确保 agent_runs 队列存在。
        queue = await declare_run_queue(channel)
        logger.info("Worker consuming queue=%s", queue.name)

        # queue.iterator() 会一直等待新消息。
        # 这是一个常驻循环，所以 worker.py 会一直运行，不会执行完就退出。
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await handle_message(message)


def main() -> None:
    # worker.py 是普通 Python 脚本，不是 ASGI 应用。
    # asyncio.run() 用来启动顶层异步函数。
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

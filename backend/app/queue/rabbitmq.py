from aio_pika import RobustChannel, RobustConnection, RobustQueue, connect_robust

from app.core.config import settings


# 这个文件只放 RabbitMQ 的“基础设施能力”：
# 1. 怎么连 RabbitMQ
# 2. 怎么开 channel
# 3. 怎么声明队列
#
# 它不关心具体发什么业务消息。
# 具体的业务发布逻辑放在 producer.py，例如 publish_run(run_id)。


async def get_rabbitmq_connection() -> RobustConnection:
    # connection 是应用和 RabbitMQ 服务器之间的 TCP/AMQP 连接。
    # settings.rabbitmq_url 来自 .env，例如：
    # amqp://ALPHA:******@rabbitmq:5672/
    #
    # 在 Docker Compose 网络里，rabbitmq 这个主机名会解析到 RabbitMQ 容器。
    # 如果在宿主机本地测试，通常要临时改成 127.0.0.1。
    # connect_robust 会创建“可自动恢复”的连接：RabbitMQ 短暂重启后，客户端会尝试重连。
    return await connect_robust(settings.rabbitmq_url)


async def get_rabbitmq_channel(connection: RobustConnection) -> RobustChannel:
    # channel 是连接上的一条逻辑通道。
    # 一个 connection 可以开多个 channel；发布消息、声明队列通常都在 channel 上完成。
    # 你可以把 connection 理解成“网线”，channel 理解成“网线里的一个会话窗口”。
    return await connection.channel()


async def declare_run_queue(channel: RobustChannel) -> RobustQueue:
    # declare_queue 是“声明队列”：如果队列不存在就创建，存在就直接复用。
    # 这个操作是幂等的，所以 producer 和后续 worker 都可以安全调用。
    #
    # settings.rabbitmq_queue 来自 .env，目前是 agent_runs。
    # 这个队列只保存 run_id，完整状态仍然在 PostgreSQL。
    # durable=True 表示队列元数据会持久化，RabbitMQ 重启后队列还在。
    # 注意：durable 只保证队列本身持久化，消息是否持久化还要看 producer.py 里的 delivery_mode。
    return await channel.declare_queue(
        settings.rabbitmq_queue,
        durable=True,
    )

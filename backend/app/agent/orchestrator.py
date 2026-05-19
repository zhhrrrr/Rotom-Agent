import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context_builder import ContextBuilder
from app.agent.zhipu_model_client import ZhipuModelClient
from app.core.logging import get_logger
from app.services import MessageService, RunService
from app.tools import ToolBroker, tool_registry

logger = get_logger(__name__)


class AgentOrchestrator:
    """Agent 核心编排器。

    Worker 只负责消费 run_id。
    Orchestrator 负责把一次 run 从 queued/running 推进到 completed/failed。

    你可以把它理解成一次 Agent 任务的“导演”：
    - 去数据库拿任务
    - 组织上下文
    - 调模型
    - 如果模型要用工具，就调用工具
    - 如果模型给出最终回答，就保存回答并结束任务
    """

    def __init__(
        self,
        db: AsyncSession,
        model_client: ZhipuModelClient | None = None,
        max_iterations: int = 5,
    ) -> None:
        # db 是当前 Worker 任务创建出来的数据库会话。
        # Orchestrator 不自己开连接，方便和 RunService/MessageService/ToolBroker 共用同一个上下文。
        self.db = db
        # 默认使用智谱客户端；测试或以后做多模型路由时，可以从外面传别的 model_client。
        self.model_client = model_client or ZhipuModelClient()
        # 防止模型一直调用工具、陷入死循环。
        # 例如模型每次都要求 list_dir，但永远不给最终回答，就最多跑 5 轮。
        self.max_iterations = max_iterations

    async def run(self, run_id: str) -> str | None:
        logger.info("Orchestrator run start run_id=%s", run_id)
        # Service 层负责具体数据库操作，Orchestrator 只编排流程。
        run_service = RunService(self.db)
        message_service = MessageService(self.db)

        # RabbitMQ 里只保存 run_id，所以 Worker 消费后要先回 PostgreSQL 查完整 Run。
        run = await run_service.get_run(run_id)
        if run is None:
            logger.error("Orchestrator run not found run_id=%s", run_id)
            return None

        # 一旦 Worker 真正开始处理，就把状态从 queued 改成 running。
        # 前端查询 /api/runs/{run_id} 时就能看到任务正在执行。
        await run_service.update_status(run_id, "running")

        try:
            # ContextBuilder 负责把 system prompt + 最近历史消息拼成模型 messages。
            # 这里拿到的 messages 会随着工具调用不断追加内容。
            messages = await ContextBuilder(self.db).build(run.session_id)
            # tool_registry.openai_tools() 只给模型“工具说明书”，不执行工具。
            # 真正执行工具是在下面 ToolBroker.invoke()。
            tools = tool_registry.openai_tools()
            # ToolBroker 负责执行工具，并把每次调用写入 tool_calls 表。
            broker = ToolBroker(db=self.db, run_id=run_id)

            for iteration in range(1, self.max_iterations + 1):
                logger.info(
                    "Orchestrator iteration start run_id=%s iteration=%s",
                    run_id,
                    iteration,
                )
                response = await self.model_client.chat(messages=messages, tools=tools)
                assistant_message = response.choices[0].message
                tool_calls = assistant_message.tool_calls or []
                logger.info(
                    "Orchestrator model response run_id=%s iteration=%s tool_calls=%s",
                    run_id,
                    iteration,
                    len(tool_calls),
                )

                if tool_calls:
                    # 模型返回 tool_calls，表示它还没有给最终答案，而是要求先执行工具。
                    #
                    # OpenAI-compatible 协议要求：
                    # 1. 先把这条 assistant tool_calls 消息放回 messages。
                    # 2. 再追加每个工具的 tool 结果消息。
                    # 3. 下一轮再把完整 messages 发给模型。
                    #
                    # 这样模型才知道：“我刚刚要求调用了工具，现在工具结果回来了。”
                    #
                    # 这一条存的是“模型的工具调用请求”，不是工具执行结果。
                    # 例子：
                    # {
                    #   "role": "assistant",
                    #   "tool_calls": [
                    #       {"id": "call_xxx", "function": {"name": "list_dir", "arguments": "{\"path\":\".\"}"}}
                    #   ]
                    # }
                    #
                    # 它表达的是：上一轮模型说“我要调用 list_dir(path='.')”。
                    messages.append(self._assistant_tool_call_message(assistant_message))

                    for tool_call in tool_calls:
                        # tool_call.function.arguments 是 JSON 字符串，需要解析成 dict。
                        # 例如 '{"path": "."}' -> {"path": "."}
                        tool_name = tool_call.function.name
                        tool_args = self._parse_tool_args(tool_call.function.arguments)
                        # 这里会真正执行 list_dir/read_file/write_file/run_shell 等工具，
                        # 并保存一条 tool_calls 记录。
                        tool_result = await broker.invoke(tool_name, tool_args)

                        # 把工具结果追加成 role="tool" 的消息。
                        # tool_call_id 必须和模型上一条 assistant tool_call 的 id 对应。
                        #
                        # 这一条存的是“工具实际执行后的结果”。
                        # 例子：
                        # {
                        #   "role": "tool",
                        #   "tool_call_id": "call_xxx",
                        #   "name": "list_dir",
                        #   "content": "{\"success\": true, \"data\": {...}}"
                        # }
                        #
                        # 它表达的是：call_xxx 这次工具调用已经执行完，结果在 content 里。
                        #
                        # 总结：
                        # - assistant tool_calls 消息：模型提出“我要调用什么工具、参数是什么”
                        # - tool 消息：系统返回“这个工具调用的执行结果是什么”
                        #
                        # 下一轮模型会同时看到这两条消息，才能把工具结果整理成最终自然语言回答。
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps(
                                    tool_result,
                                    ensure_ascii=False,
                                ),
                            }
                        )

                    # 工具执行完后不能直接结束，因为最终回答还需要模型根据工具结果生成。
                    # 所以 continue 进入下一轮模型调用。
                    continue

                # 没有 tool_calls，说明模型已经给出最终自然语言回答。
                # 这时保存 assistant message，并把 Run 标记为 completed。
                # 存储工具记录的逻辑在broker中
                content = assistant_message.content or ""
                await message_service.save_assistant_message(
                    session_id=run.session_id,
                    run_id=run_id,
                    content=content,
                )
                await run_service.update_status(run_id, "completed")
                logger.info("Orchestrator run completed run_id=%s", run_id)
                return content

            error = f"Agent exceeded max_iterations={self.max_iterations}"
            await run_service.update_status(run_id, "failed", error=error)
            logger.error("Orchestrator run failed run_id=%s error=%s", run_id, error)
            return None

        except Exception as exc:
            # 任何未处理异常都要落到 failed。
            # 这样任务不会一直卡在 running，前端也能看到 error。
            logger.exception("Orchestrator exception run_id=%s", run_id)
            await run_service.update_status(run_id, "failed", error=str(exc))
            return None

    async def execute(self, run_id: str) -> str | None:
        # 兼容第 15 步里已经接入的旧方法名。
        # 后续正式入口统一用 run(run_id)。
        return await self.run(run_id)

    def _assistant_tool_call_message(self, assistant_message: Any) -> dict[str, Any]:
        # 模型请求调用工具时，下一轮 messages 里必须保留这条 assistant 消息。
        # 它告诉模型：“上一轮你要求调用了这些工具”。
        return {
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in assistant_message.tool_calls or []
            ],
        }

    def _parse_tool_args(self, raw_arguments: str | None) -> dict[str, Any]:
        # OpenAI-compatible tool call 的 arguments 是 JSON 字符串。
        # 例如："{\"path\": \".\"}"。
        if not raw_arguments:
            # 有些模型可能返回空参数，统一当成空 dict。
            return {}

        parsed = json.loads(raw_arguments)
        # 工具参数必须是对象，不能是 list/string/int。
        # 因为 ToolBroker 最终会用 **tool_args 展开参数。
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object")

        return parsed

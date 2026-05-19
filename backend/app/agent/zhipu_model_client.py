from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ZhipuModelClient:
    """智谱 GLM 的最小异步客户端。

    这一层只负责“怎么调用模型”，不负责业务流程。
    后面做多模型路由时，可以让 Router 决定用哪个 ModelClient。
    """

    def __init__(self) -> None:
        # 智谱提供 OpenAI-compatible 接口，所以可以直接复用 openai SDK。
        # api_key / base_url 都从 .env 读取，避免把密钥或地址写死在代码里。
        self.client = AsyncOpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
        )
        # 当前模型名也来自 .env，例如 glm-4.5-air。
        self.model = settings.zhipu_model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ):
        logger.info(
            "Model call start model=%s messages=%s tools=%s",
            self.model,
            len(messages),
            len(tools or []),
        )
        # messages 是对话上下文，结构类似：
        # [{"role": "user", "content": "你好"}]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        # tools 只有在需要函数调用 / 工具调用时才传。
        # tool_choice="auto" 表示让模型自己判断是否需要调用工具。
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**kwargs)
            logger.info(
                "Model call end model=%s choices=%s",
                self.model,
                len(response.choices),
            )
            return response
        except Exception:
            logger.exception("Model call exception model=%s", self.model)
            raise

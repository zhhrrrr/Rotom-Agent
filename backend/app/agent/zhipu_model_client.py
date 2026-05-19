from copy import deepcopy
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.services.model_call_service import ModelCallService

logger = get_logger(__name__)


class ZhipuModelClient:
    """智谱 GLM 的最小异步客户端。

    这一层负责“怎么调用模型”和“怎么记录模型调用审计”。
    Orchestrator 只需要传入 run/user/workspace/session 上下文。
    后面做多模型路由时，可以让 Router 决定用哪个 ModelClient。
    """

    provider = "zhipu"

    def __init__(self, db: AsyncSession | None = None) -> None:
        # 智谱提供 OpenAI-compatible 接口，所以可以直接复用 openai SDK。
        # api_key / base_url 都从 .env 读取，避免把密钥或地址写死在代码里。
        self.client = AsyncOpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
        )
        # 当前模型名也来自 .env，例如 glm-4.5-air。
        self.model = settings.zhipu_model
        # db 可选：独立测试脚本可以不记录 model_calls，真实 Worker 路径会传入 db。
        self.db = db
        # 保存最近一次模型调用耗时，给 Orchestrator 写 event_logs payload 用。
        self.last_latency_ms: int | None = None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ):
        logger.info(
            "Model call start model=%s messages=%s tools=%s",
            self.model,
            len(messages),
            len(tools or []),
        )
        started_at = perf_counter()
        request_messages = deepcopy(messages)
        request_tools = deepcopy(tools) if tools is not None else None
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
            self.last_latency_ms = int((perf_counter() - started_at) * 1000)
            await self._record_model_call(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
                request_messages=request_messages,
                request_tools=request_tools,
                response_message=self._dump_model_object(response.choices[0].message),
                prompt_tokens=getattr(getattr(response, "usage", None), "prompt_tokens", None),
                completion_tokens=getattr(
                    getattr(response, "usage", None),
                    "completion_tokens",
                    None,
                ),
                latency_ms=self.last_latency_ms,
                status="completed",
            )
            logger.info(
                "Model call end model=%s choices=%s latency_ms=%s",
                self.model,
                len(response.choices),
                self.last_latency_ms,
            )
            return response
        except Exception as exc:
            self.last_latency_ms = int((perf_counter() - started_at) * 1000)
            await self._record_model_call(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
                request_messages=request_messages,
                request_tools=request_tools,
                latency_ms=self.last_latency_ms,
                status="failed",
                error=str(exc),
            )
            logger.exception("Model call exception model=%s", self.model)
            raise

    async def _record_model_call(
        self,
        user_id: str | None,
        workspace_id: str | None,
        session_id: str | None,
        run_id: str | None,
        request_messages: list[dict[str, Any]],
        request_tools: list[dict[str, Any]] | None,
        status: str,
        response_message: dict[str, Any] | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        # 独立调用模型时可以不传 db / run 上下文；真实 run 路径必须传完整上下文。
        if self.db is None:
            return
        if not all([user_id, workspace_id, session_id, run_id]):
            logger.warning(
                "Skip model_call record because context is incomplete "
                "user_id=%s workspace_id=%s session_id=%s run_id=%s",
                user_id,
                workspace_id,
                session_id,
                run_id,
            )
            return

        await ModelCallService(self.db).record(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            provider=self.provider,
            model=self.model,
            request_messages=request_messages,
            request_tools=request_tools,
            response_message=response_message,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status=status,
            error=error,
        )

    def _dump_model_object(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        return {"value": str(value)}

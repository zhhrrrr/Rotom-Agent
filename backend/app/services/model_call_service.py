from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModelCall


class ModelCallService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        user_id: str,
        workspace_id: str,
        session_id: str,
        run_id: str,
        provider: str,
        model: str,
        request_messages: list[dict[str, Any]],
        request_tools: list[dict[str, Any]] | None,
        status: str,
        response_message: dict[str, Any] | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> ModelCall:
        model_call = ModelCall(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            provider=provider,
            model=model,
            request_messages=request_messages,
            request_tools=request_tools,
            response_message=response_message,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status=status,
            error=error,
        )
        self.db.add(model_call)
        await self.db.commit()
        await self.db.refresh(model_call)
        return model_call

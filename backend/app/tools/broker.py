from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID, Run, ToolCall
from app.tools.registry import ToolRegistry, tool_registry


ToolResult = dict[str, Any]
logger = get_logger(__name__)


class ToolBroker:
    """工具调用入口。

    Registry 负责“有哪些工具”，Broker 负责“调用工具并记录数据库”。
    这样后面 AgentOrchestrator 不需要知道每个工具的函数在哪里。
    """

    def __init__(
        self,
        db: AsyncSession,
        run_id: str,
        registry: ToolRegistry = tool_registry,
    ) -> None:
        # db 用来写 tool_calls 表。
        self.db = db
        # 每次工具调用都属于某一次 run。
        self.run_id = run_id
        # 默认使用全局 tool_registry，测试时也可以传自定义 registry。
        self.registry = registry

    async def invoke(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        user_id, workspace_id = await self._run_scope()
        logger.info(
            "Tool call start run_id=%s tool_name=%s args=%s",
            self.run_id,
            tool_name,
            args,
        )
        tool = self.registry.get(tool_name)
        if tool is None:
            result = {
                "success": False,
                "tool_name": tool_name,
                "data": {},
                "error": f"Unknown tool: {tool_name}",
            }
            await self._save_tool_call(
                tool_name=tool_name,
                args=args,
                result=result,
                status="failed",
                error=result["error"],
                user_id=user_id,
                workspace_id=workspace_id,
            )
            logger.error(
                "Tool call end run_id=%s tool_name=%s success=false error=%s",
                self.run_id,
                tool_name,
                result["error"],
            )
            return result

        tool_call = ToolCall(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=self.run_id,
            tool_name=tool_name,
            tool_args=args,
            status="running",
        )
        self.db.add(tool_call)
        await self.db.commit()
        await self.db.refresh(tool_call)

        try:
            # args 来自模型 tool call，一般是 {"path": "..."}。
            # **args 会把它展开成 list_dir(path="...") 这种调用。
            raw_data = tool.handler(**args)
            if isinstance(raw_data, Awaitable):
                raw_data = await raw_data

            result = {
                "success": True,
                "tool_name": tool_name,
                "data": self._normalize_data(raw_data),
            }

            tool_call.status = "completed"
            tool_call.tool_result = result
            tool_call.error = None
            tool_call.finished_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(tool_call)
            logger.info(
                "Tool call end run_id=%s tool_name=%s success=true tool_call_id=%s",
                self.run_id,
                tool_name,
                tool_call.id,
            )
            return result

        except Exception as exc:
            logger.exception(
                "Tool call exception run_id=%s tool_name=%s",
                self.run_id,
                tool_name,
            )
            result = {
                "success": False,
                "tool_name": tool_name,
                "data": {},
                "error": str(exc),
            }

            tool_call.status = "failed"
            tool_call.tool_result = result
            tool_call.error = str(exc)
            tool_call.finished_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(tool_call)
            logger.error(
                "Tool call end run_id=%s tool_name=%s success=false tool_call_id=%s error=%s",
                self.run_id,
                tool_name,
                tool_call.id,
                str(exc),
            )
            return result

    async def _save_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: ToolResult,
        status: str,
        error: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> ToolCall:
        tool_call = ToolCall(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=self.run_id,
            tool_name=tool_name,
            tool_args=args,
            tool_result=result,
            status=status,
            error=error,
            finished_at=datetime.now(UTC),
        )
        self.db.add(tool_call)
        await self.db.commit()
        await self.db.refresh(tool_call)
        return tool_call

    async def _run_scope(self) -> tuple[str, str]:
        run = await self.db.get(Run, self.run_id)
        if run is None:
            return DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID
        return run.user_id, run.workspace_id

    def _normalize_data(self, raw_data: Any) -> dict[str, Any]:
        # Broker 对外统一返回 {"data": {...}}。
        # list_dir 原始返回 list，所以包成 entries；read_file 原始返回 str，所以包成 content。
        if isinstance(raw_data, dict):
            return raw_data
        if isinstance(raw_data, list):
            return {"entries": raw_data}
        if isinstance(raw_data, str):
            return {"content": raw_data}

        return {"result": raw_data}

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import DEFAULT_USER_ID, DEFAULT_WORKSPACE_ID, Run, ToolCall, Workspace
from app.services.permission_service import PermissionService
from app.services.trace_service import TraceService
from app.streaming import RunStreamPublisher
from app.tools.registry import ToolRegistry, tool_registry
from app.tools.result import ToolResult
from app.runtime import RuntimeManager


logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolRunScope:
    user_id: str
    workspace_id: str
    session_id: str | None
    workspace_root: str | None


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
        permission_service: PermissionService | None = None,
        runtime_manager: RuntimeManager | None = None,
        trace_service: TraceService | None = None,
        stream_publisher: RunStreamPublisher | None = None,
    ) -> None:
        # db 用来写 tool_calls 表。
        self.db = db
        # 每次工具调用都属于某一次 run。
        self.run_id = run_id
        # 默认使用全局 tool_registry，测试时也可以传自定义 registry。
        self.registry = registry
        # 权限服务集中判断风险等级、运行时和危险命令。
        self.permission_service = permission_service or PermissionService()
        # RuntimeManager 负责把 ToolSpec.runtime_type 映射到实际执行器。
        self.runtime_manager = runtime_manager or RuntimeManager()
        # Broker 内部写工具事件，避免 Orchestrator 重复关心工具审计细节。
        self.trace_service = trace_service or TraceService(db)
        self.stream_publisher = stream_publisher

    async def invoke_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        scope = await self._run_scope()
        logger.info(
            "Tool call start run_id=%s tool_name=%s args=%s",
            self.run_id,
            tool_name,
            args,
        )
        tool = self.registry.get(tool_name)
        if tool is None:
            result = ToolResult(success=False, data=None, error=f"Unknown tool: {tool_name}")
            tool_call = await self._save_tool_call(
                tool_name=tool_name,
                args=args,
                result=result,
                status="failed",
                error=result.error,
                scope=scope,
            )
            await self._log_tool_failed(tool_name, args, result.error, scope, tool_call=tool_call)
            await self._publish_tool_finished_event(
                tool_name=tool_name,
                args=args,
                result=result,
                scope=scope,
                tool_call=tool_call,
            )
            logger.error(
                "Tool call end run_id=%s tool_name=%s success=false error=%s",
                self.run_id,
                tool_name,
                result.error,
            )
            return result

        if not tool.enabled:
            result = ToolResult(success=False, data=None, error=f"Tool is disabled: {tool_name}")
            tool_call = await self._save_tool_call(
                tool_name=tool_name,
                args=args,
                result=result,
                status="failed",
                error=result.error,
                scope=scope,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
            await self._log_tool_failed(tool_name, args, result.error, scope, tool, tool_call)
            await self._publish_tool_finished_event(
                tool_name=tool_name,
                args=args,
                result=result,
                scope=scope,
                tool_call=tool_call,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
            logger.error(
                "Tool call denied run_id=%s tool_name=%s error=%s",
                self.run_id,
                tool_name,
                result.error,
            )
            return result

        permission = await self.permission_service.evaluate_tool_use(
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            tool_name=tool.name,
            risk_level=tool.risk_level,
            runtime_type=tool.runtime_type,
            tool_args=args,
        )
        if not permission.allowed:
            result = ToolResult(
                success=False,
                data=None,
                error=permission.reason or "Tool use is not allowed",
            )
            tool_call = await self._save_tool_call(
                tool_name=tool_name,
                args=args,
                result=result,
                status="failed",
                error=result.error,
                scope=scope,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
            await self._log_tool_failed(tool_name, args, result.error, scope, tool, tool_call)
            await self._publish_tool_finished_event(
                tool_name=tool_name,
                args=args,
                result=result,
                scope=scope,
                tool_call=tool_call,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
            logger.error(
                "Tool call denied run_id=%s tool_name=%s risk_level=%s runtime_type=%s error=%s",
                self.run_id,
                tool_name,
                tool.risk_level,
                tool.runtime_type,
                result.error,
            )
            return result

        try:
            runtime = self.runtime_manager.select(tool)
        except ValueError as exc:
            result = ToolResult(success=False, data=None, error=str(exc))
            tool_call = await self._save_tool_call(
                tool_name=tool_name,
                args=args,
                result=result,
                status="failed",
                error=result.error,
                scope=scope,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
            await self._log_tool_failed(tool_name, args, result.error, scope, tool, tool_call)
            await self._publish_tool_finished_event(
                tool_name=tool_name,
                args=args,
                result=result,
                scope=scope,
                tool_call=tool_call,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
            return result

        tool_call = ToolCall(
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            run_id=self.run_id,
            tool_name=tool_name,
            tool_args=args,
            status="running",
            runtime_type=tool.runtime_type,
            risk_level=tool.risk_level,
        )
        self.db.add(tool_call)
        await self.db.commit()
        await self.db.refresh(tool_call)
        await self._log_tool_started(tool_call, args, scope)
        await self._publish_tool_started_event(tool_call, args, scope)

        try:
            raw_data = await runtime.execute(tool, args, scope.workspace_root)
            result = ToolResult(success=True, data=self._normalize_data(raw_data))

            tool_call.status = "completed"
            tool_call.tool_result = result.to_model_message()
            tool_call.error = None
            tool_call.finished_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(tool_call)
            await self._log_tool_completed(tool_call, result, scope)
            await self._publish_tool_delta_event(tool_call, result, scope)
            await self._publish_tool_finished_event(
                tool_name=tool_name,
                args=args,
                result=result,
                scope=scope,
                tool_call=tool_call,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
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
            result = ToolResult(success=False, data=None, error=str(exc))

            tool_call.status = "failed"
            tool_call.tool_result = result.to_model_message()
            tool_call.error = str(exc)
            tool_call.finished_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(tool_call)
            await self._log_tool_failed(tool_name, args, result.error, scope, tool, tool_call)
            await self._publish_tool_finished_event(
                tool_name=tool_name,
                args=args,
                result=result,
                scope=scope,
                tool_call=tool_call,
                runtime_type=tool.runtime_type,
                risk_level=tool.risk_level,
            )
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
        scope: ToolRunScope | None = None,
        runtime_type: str | None = None,
        risk_level: str | None = None,
    ) -> ToolCall:
        scope = scope or ToolRunScope(
            user_id=DEFAULT_USER_ID,
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_id=None,
            workspace_root=None,
        )
        tool_call = ToolCall(
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            run_id=self.run_id,
            tool_name=tool_name,
            tool_args=args,
            tool_result=result.to_model_message(),
            status=status,
            runtime_type=runtime_type,
            risk_level=risk_level,
            error=error,
            finished_at=datetime.now(UTC),
        )
        self.db.add(tool_call)
        await self.db.commit()
        await self.db.refresh(tool_call)
        return tool_call

    async def _run_scope(self) -> ToolRunScope:
        run = await self.db.get(Run, self.run_id)
        if run is None:
            return ToolRunScope(
                user_id=DEFAULT_USER_ID,
                workspace_id=DEFAULT_WORKSPACE_ID,
                session_id=None,
                workspace_root=None,
            )

        workspace = await self.db.get(Workspace, run.workspace_id)
        workspace_root = workspace.root_path if workspace is not None else None
        return ToolRunScope(
            user_id=run.user_id,
            workspace_id=run.workspace_id,
            session_id=run.session_id,
            workspace_root=workspace_root,
        )

    async def _log_tool_started(
        self,
        tool_call: ToolCall,
        args: dict[str, Any],
        scope: ToolRunScope,
    ) -> None:
        await self.trace_service.log(
            event_type="tool.call.started",
            message=f"Tool call started: {tool_call.tool_name}",
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            session_id=scope.session_id,
            run_id=self.run_id,
            payload={
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.tool_name,
                "tool_args": args,
                "runtime_type": tool_call.runtime_type,
                "risk_level": tool_call.risk_level,
            },
        )

    async def _log_tool_completed(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        scope: ToolRunScope,
    ) -> None:
        await self.trace_service.log(
            event_type="tool.call.completed",
            message=f"Tool call completed: {tool_call.tool_name}",
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            session_id=scope.session_id,
            run_id=self.run_id,
            payload={
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.tool_name,
                "success": result.success,
                "runtime_type": tool_call.runtime_type,
                "risk_level": tool_call.risk_level,
            },
        )

    async def _log_tool_failed(
        self,
        tool_name: str,
        args: dict[str, Any],
        error: str | None,
        scope: ToolRunScope,
        tool: Any | None = None,
        tool_call: ToolCall | None = None,
    ) -> None:
        await self.trace_service.log(
            event_type="tool.call.failed",
            message=f"Tool call failed: {tool_name}",
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            session_id=scope.session_id,
            run_id=self.run_id,
            payload={
                "tool_call_id": tool_call.id if tool_call is not None else None,
                "tool_name": tool_name,
                "tool_args": args,
                "runtime_type": getattr(tool, "runtime_type", None),
                "risk_level": getattr(tool, "risk_level", None),
                "error": error,
            },
        )

    async def _publish_tool_started_event(
        self,
        tool_call: ToolCall,
        args: dict[str, Any],
        scope: ToolRunScope,
    ) -> None:
        await self._publish_tool_event(
            event_type="tool_started",
            content=f"{tool_call.tool_name} started",
            scope=scope,
            payload={
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.tool_name,
                "tool_args": args,
                "runtime_type": tool_call.runtime_type,
                "risk_level": tool_call.risk_level,
            },
        )

    async def _publish_tool_delta_event(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        scope: ToolRunScope,
    ) -> None:
        content = self._tool_result_display(result)
        if not content:
            return

        await self._publish_tool_event(
            event_type="tool_delta",
            content=content,
            scope=scope,
            payload={
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.tool_name,
                "success": result.success,
            },
        )

    async def _publish_tool_finished_event(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: ToolResult,
        scope: ToolRunScope,
        tool_call: ToolCall,
        runtime_type: str | None = None,
        risk_level: str | None = None,
    ) -> None:
        await self._publish_tool_event(
            event_type="tool_finished",
            content="completed" if result.success else result.error or "failed",
            scope=scope,
            payload={
                "tool_call_id": tool_call.id,
                "tool_name": tool_name,
                "tool_args": args,
                "success": result.success,
                "error": result.error,
                "runtime_type": runtime_type or tool_call.runtime_type,
                "risk_level": risk_level or tool_call.risk_level,
            },
        )

    async def _publish_tool_event(
        self,
        event_type: str,
        content: str,
        scope: ToolRunScope,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.stream_publisher is None or scope.session_id is None:
            return

        await self.stream_publisher.publish(
            run_id=self.run_id,
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            session_id=scope.session_id,
            event_type=event_type,
            role="tool",
            content=content,
            payload=payload,
        )

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

    def _tool_result_display(self, result: ToolResult, limit: int = 2000) -> str:
        if not result.success:
            return result.error or ""

        data = result.data
        if isinstance(data, dict):
            if data.get("stdout") or data.get("stderr"):
                text = "\n".join(
                    part
                    for part in (
                        str(data.get("stdout") or "").rstrip(),
                        str(data.get("stderr") or "").rstrip(),
                    )
                    if part
                )
            elif "content" in data:
                text = str(data["content"])
            else:
                text = json.dumps(data, ensure_ascii=False)
        else:
            text = str(data or "")

        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[truncated]"

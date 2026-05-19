from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

from app.runtime.base import safe_join

if TYPE_CHECKING:
    from app.tools.registry import ToolSpec


class LocalRuntime:
    runtime_type = "local"

    async def execute(
        self,
        tool: ToolSpec,
        args: dict[str, Any],
        workspace_root: str | None,
    ) -> Any:
        if workspace_root is None:
            raise PermissionError("workspace root is required")

        safe_args = self._validate_path_args(args, workspace_root)
        raw_data = tool.handler(**safe_args, workspace_root=workspace_root)
        if isinstance(raw_data, Awaitable):
            raw_data = await raw_data
        return raw_data

    def _validate_path_args(
        self,
        args: dict[str, Any],
        workspace_root: str,
    ) -> dict[str, Any]:
        safe_args = dict(args)
        for key in ("path", "target_path", "source_path"):
            value = safe_args.get(key)
            if isinstance(value, str):
                safe_join(workspace_root, value)
        return safe_args

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.tools.registry import ToolSpec


class ToolRuntime(Protocol):
    runtime_type: str

    async def execute(
        self,
        tool: ToolSpec,
        args: dict[str, Any],
        workspace_root: str | None,
    ) -> Any:
        ...


def safe_join(root: str, relative_path: str) -> Path:
    if "\x00" in relative_path:
        raise PermissionError("path escape detected")

    windows_path = PureWindowsPath(relative_path)
    if windows_path.is_absolute() or windows_path.drive:
        raise PermissionError("path escape detected")

    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        raise PermissionError("path escape detected")

    root_path = Path(root).resolve()
    target = (root_path / raw_path).resolve()
    try:
        target.relative_to(root_path)
    except ValueError as exc:
        raise PermissionError("path escape detected") from exc

    return target

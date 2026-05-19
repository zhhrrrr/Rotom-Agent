from __future__ import annotations

from typing import TYPE_CHECKING

from app.runtime.base import ToolRuntime
from app.runtime.docker_runtime import DockerRuntime
from app.runtime.local_runtime import LocalRuntime

if TYPE_CHECKING:
    from app.tools.registry import ToolSpec


class RuntimeManager:
    def __init__(
        self,
        local_runtime: LocalRuntime | None = None,
        docker_runtime: DockerRuntime | None = None,
    ) -> None:
        self.local_runtime = local_runtime or LocalRuntime()
        self.docker_runtime = docker_runtime or DockerRuntime()

    def select(self, tool_spec: ToolSpec) -> ToolRuntime:
        if tool_spec.runtime_type == "docker":
            return self.docker_runtime
        return self.local_runtime

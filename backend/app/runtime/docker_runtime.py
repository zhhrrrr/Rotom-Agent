from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.runtime.base import safe_join

if TYPE_CHECKING:
    from app.tools.registry import ToolSpec


DOCKER_IMAGE = "python:3.11-slim"
DOCKER_TIMEOUT_SECONDS = 20
MAX_STDOUT_CHARS = 8_000
MAX_STDERR_CHARS = 8_000


class DockerRuntime:
    runtime_type = "docker"

    async def execute(
        self,
        tool: ToolSpec,
        args: dict[str, Any],
        workspace_root: str | None,
    ) -> Any:
        if tool.name != "run_shell":
            raise ValueError("DockerRuntime only supports run_shell in v1")
        if workspace_root is None:
            raise PermissionError("workspace root is required")

        workspace_path = safe_join(workspace_root, ".")
        host_workspace_path = self._host_workspace_path(workspace_path)
        command = str(args.get("command", ""))
        if not command:
            raise ValueError("Command cannot be empty")

        return await asyncio.to_thread(
            self._run_shell_in_container,
            host_workspace_path,
            command,
        )

    def _host_workspace_path(self, workspace_path: Path) -> Path:
        if settings.host_workspace_root is None:
            return workspace_path

        container_root = settings.workspace_root.resolve()
        try:
            relative_path = workspace_path.resolve().relative_to(container_root)
        except ValueError as exc:
            raise PermissionError("workspace path escapes WORKSPACE_ROOT") from exc

        return (settings.host_workspace_root.resolve() / relative_path).resolve()

    def _run_shell_in_container(self, workspace_path: Path, command: str) -> dict[str, Any]:
        docker_command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace_path}:/workspace",
            "-w",
            "/workspace",
            DOCKER_IMAGE,
            "bash",
            "-lc",
            command,
        ]
        try:
            completed = subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                timeout=DOCKER_TIMEOUT_SECONDS,
                check=False,
            )
            return {
                "command": command,
                "runtime": "docker",
                "image": DOCKER_IMAGE,
                "exit_code": completed.returncode,
                "stdout": self._truncate(completed.stdout, MAX_STDOUT_CHARS),
                "stderr": self._truncate(completed.stderr, MAX_STDERR_CHARS),
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "command": command,
                "runtime": "docker",
                "image": DOCKER_IMAGE,
                "exit_code": None,
                "stdout": self._truncate(exc.stdout or "", MAX_STDOUT_CHARS),
                "stderr": self._truncate(exc.stderr or "", MAX_STDERR_CHARS),
                "timed_out": True,
            }
        except FileNotFoundError as exc:
            raise RuntimeError("docker command is not available") from exc

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[truncated]"

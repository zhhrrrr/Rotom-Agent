import shlex
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str | None = None


DANGEROUS_COMMANDS = {
    "chmod",
    "chown",
    "curl",
    "dd",
    "docker",
    "git",
    "kill",
    "mkfs",
    "mv",
    "nc",
    "pip",
    "python",
    "reboot",
    "rm",
    "scp",
    "shutdown",
    "ssh",
    "sudo",
    "wget",
}

DANGEROUS_TOKENS = {
    ";",
    "&&",
    "||",
    "|",
    ">",
    ">>",
    "<",
    "`",
    "$(",
}


class PermissionService:
    """Minimal v1 tool permission policy.

    This is intentionally not RBAC yet. It centralizes the first set of hard
    rules so ToolBroker does not need to know why a tool is safe or unsafe.
    """

    async def can_use_tool(
        self,
        user_id: str,
        workspace_id: str,
        tool_name: str,
        risk_level: str,
        runtime_type: str,
    ) -> bool:
        decision = await self.evaluate_tool_use(
            user_id=user_id,
            workspace_id=workspace_id,
            tool_name=tool_name,
            risk_level=risk_level,
            runtime_type=runtime_type,
        )
        return decision.allowed

    async def evaluate_tool_use(
        self,
        user_id: str,
        workspace_id: str,
        tool_name: str,
        risk_level: str,
        runtime_type: str,
        tool_args: dict[str, Any] | None = None,
    ) -> PermissionDecision:
        if risk_level == "low":
            return PermissionDecision(allowed=True)

        if risk_level == "medium":
            # Medium risk is allowed in v1, but ToolBroker records risk/runtime
            # into tool_calls so it remains auditable.
            return PermissionDecision(allowed=True)

        if risk_level == "high":
            if runtime_type != "docker":
                return PermissionDecision(
                    allowed=False,
                    reason="High risk tools must use DockerRuntime",
                )
            if tool_name == "run_shell":
                command = str((tool_args or {}).get("command", ""))
                dangerous_reason = self._dangerous_command_reason(command)
                if dangerous_reason is not None:
                    return PermissionDecision(allowed=False, reason=dangerous_reason)
            return PermissionDecision(allowed=True)

        return PermissionDecision(
            allowed=False,
            reason=f"Unknown tool risk level: {risk_level}",
        )

    def _dangerous_command_reason(self, command: str) -> str | None:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Invalid shell command: {exc}"

        if not parts:
            return "Command cannot be empty"

        for part in parts:
            if part in DANGEROUS_TOKENS:
                return f"Dangerous shell token is not allowed: {part}"
            if any(token in part for token in DANGEROUS_TOKENS):
                return f"Dangerous shell syntax is not allowed: {part}"

        command_name = parts[0]
        if parts in (
            ["python", "--version"],
            ["python3", "--version"],
            ["pip", "--version"],
            ["pip3", "--version"],
        ):
            return None

        if command_name in DANGEROUS_COMMANDS:
            return f"Dangerous command is not allowed: {command_name}"

        return None

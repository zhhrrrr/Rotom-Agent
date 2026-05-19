# Tool Permission Policy

本文总结 Rotom Agent v1 的工具定义和权限策略。

## ToolSpec

`ToolSpec` 现在包含：

- `name`: 工具名。
- `description`: 给模型看的工具说明。
- `parameters`: OpenAI-compatible JSON Schema。
- `handler`: 实际执行函数。
- `risk_level`: `low` / `medium` / `high`。
- `runtime_type`: `local` / `docker`。
- `enabled`: 是否暴露给模型并允许 Broker 执行，默认 `True`。

当前工具配置：

| 工具 | runtime_type | risk_level |
| --- | --- | --- |
| `list_dir` | `local` | `low` |
| `read_file` | `local` | `low` |
| `write_file` | `local` | `medium` |
| `run_shell` | `docker` | `high` |

`ToolRegistry.openai_tools()` 只会把 `enabled=True` 的工具暴露给模型。

## PermissionService

`PermissionService` 是 v1 的最小工具权限服务，当前不做复杂 RBAC。

规则：

- `low`: 允许。
- `medium`: 允许，但由 `tool_calls` 记录 `risk_level` 和 `runtime_type`。
- `high`: 只允许 `runtime_type="docker"`。
- 危险命令直接禁止。

危险命令和危险 shell 语法由 `PermissionService` 先做入口拦截，`shell_tools.py` 仍保留自己的执行前校验作为第二道保险：

- 危险命令示例：`rm`、`curl`、`wget`、`ssh`、`sudo`、`docker`。
- 危险语法示例：`;`、`&&`、`|`、`>`、`$(`。
- `python --version`、`python3 --version`、`pip --version`、`pip3 --version` 属于显式允许的只读版本查询。

## ToolBroker 执行顺序

`ToolBroker.invoke_tool(...)` 是 v1 的统一工具入口。

1. 根据 run 解析 `user_id`、`workspace_id`、`session_id`、`workspace_root`。
2. `ToolRegistry.get(tool_name)` 查找 `ToolSpec`。
3. 拒绝未知工具。
4. 拒绝 disabled 工具。
5. 调用 `PermissionService.evaluate_tool_use(...)`。
6. 调用 `RuntimeManager.select(tool_spec)`。
7. 写入 `tool_calls(status="running")`，包含 `risk_level` 和 `runtime_type`。
8. 写入 `event_logs.tool.call.started`。
9. 通过 Runtime 执行 handler。
10. 成功时更新 `tool_calls(status="completed")`，写入 `event_logs.tool.call.completed`。
11. 失败时更新 `tool_calls(status="failed")`，写入 `event_logs.tool.call.failed`。
12. 返回统一 `ToolResult`。

这样即使模型请求了危险工具，也会留下结构化审计记录。

## RuntimeManager

`RuntimeManager` 根据 `ToolSpec.runtime_type` 选择 Runtime：

- `local`: `LocalRuntime`
- `docker`: `DockerRuntime`

当前 `DockerRuntime` 是高风险工具的运行边界入口；`run_shell` 自身仍会执行严格白名单校验。

Runtime 代码位于：

- `backend/app/runtime/base.py`
- `backend/app/runtime/local_runtime.py`
- `backend/app/runtime/docker_runtime.py`
- `backend/app/runtime/runtime_manager.py`

`LocalRuntime` 在执行工具前会校验路径参数，确保 `path`、`target_path`、`source_path` 最终都落在当前 `workspace.root_path` 下。

禁止的路径示例：

- `../../etc/passwd`
- `/root/.ssh/id_rsa`
- `C:\Users\xxx`

`DockerRuntime` v1 先服务 `run_shell`，执行方式：

```bash
docker run --rm \
  -v <workspace>:/workspace \
  -w /workspace \
  python:3.11-slim \
  bash -lc "<command>"
```

它会限制超时和 stdout/stderr 长度，并在执行结束后删除临时容器。

运行要求：

- backend/worker 镜像内需要 docker CLI。
- worker 需要挂载 `/var/run/docker.sock`。
- worker 需要设置 `HOST_WORKSPACE_ROOT`，把容器内 `WORKSPACE_ROOT` 映射到宿主机真实 workspace 路径。

## ToolResult

`ToolResult` 是工具返回给 Orchestrator 的统一格式：

```python
class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
    display: str | None = None
```

回填给模型时统一使用：

```json
{
  "success": true,
  "data": "...",
  "error": null
}
```

`display` 用于以后给前端展示更友好的摘要，不直接回填给模型。

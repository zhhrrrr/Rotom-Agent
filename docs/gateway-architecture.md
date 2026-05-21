# Gateway Architecture

本文总结 Rotom Agent v1 中 Chat Gateway 的实现架构和业务职责。

## 目标

v0 的 `/api/chat` 直接承担了太多事情：

- 接收 HTTP 请求
- 解析 session
- 保存 user message
- 创建 run
- 投递 RabbitMQ
- 写事件日志

v1 将这些入口编排逻辑迁移到 Gateway 层，让 `chat.py` 只负责 HTTP 接入，业务流程由 `GatewayService` 统一处理。

## 分层结构

当前 Gateway 相关文件：

```text
backend/app/api/chat.py
backend/app/gateway/gateway_service.py
backend/app/gateway/request_context.py
backend/app/gateway/session_router.py
backend/app/gateway/run_router.py
backend/app/schemas/chat.py
```

职责划分：

| 文件 | 职责 |
| --- | --- |
| `api/chat.py` | FastAPI HTTP 入口，只做依赖注入和调用 Gateway |
| `gateway/gateway_service.py` | Chat 请求总编排，负责完整业务流程 |
| `gateway/request_context.py` | 在 Gateway 流程中传递 user、workspace、session、run 等上下文 |
| `gateway/session_router.py` | 创建新 session 或校验并复用已有 session |
| `gateway/run_router.py` | 检查 active run，并创建 queued run |
| `schemas/chat.py` | 定义 `ChatRequest`、`ChatResponse`、`RunDebugResponse` |

## HTTP 入口

`chat.py` 的目标是保持薄：

```python
@router.post("/chat", response_model=ChatResponse)
async def create_chat_run(
    request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChatResponse:
    gateway = GatewayService(db)
    return await gateway.handle_chat(current_user, request)
```

这里的业务含义：

- `get_current_user` 负责 JWT 鉴权。
- `get_session` 负责提供数据库会话。
- `ChatRequest` 只描述用户输入。
- 真正的 chat 业务不放在 API 层，而是交给 `GatewayService`。

## ChatRequest

v1 的请求体：

```json
{
  "workspace_id": "workspace_xxx",
  "session_id": "sess_xxx",
  "message": "你好"
}
```

字段说明：

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| `message` | 是 | 用户输入 |
| `workspace_id` | 否 | 不传时使用当前用户默认 workspace |
| `session_id` | 否 | 不传时创建新 session |

## RequestContext

`RequestContext` 是 Gateway 内部流转对象。

它把一次请求中逐步解析出来的对象集中放在一起：

```text
user
message
requested_workspace_id
requested_session_id
workspace
session
run
```

这样后续步骤不需要反复传很多参数，也能清楚看到 Gateway 当前已经解析到哪一步。

## GatewayService 流程

`GatewayService.handle_chat()` 是 v1 chat 入口编排核心。

当前流程：

1. 构建 `RequestContext`
2. 解析 workspace
3. 写 `chat.request.received`
4. 写 `gateway.auth.checked`
5. 写 `workspace.resolved`
6. 解析 session
7. 写 `session.resolved`
8. 检查当前 session 是否已有 active run
9. 保存 user message
10. 创建 queued run
11. 回填 user message 的 `run_id`
12. 写 `run.created`
13. 投递 `run_id` 到 RabbitMQ
14. 写 `run.queued`
15. 返回 `ChatResponse`

返回给前端的是 queued 状态：

```json
{
  "user_id": "user_xxx",
  "workspace_id": "workspace_xxx",
  "session_id": "sess_xxx",
  "run_id": "run_xxx",
  "status": "queued"
}
```

最终回答不在 `/api/chat` 同步返回，而是通过：

```text
GET /api/runs/{run_id}
```

查询。

## Workspace 解析

Gateway 不信任请求体里的用户身份，只使用 JWT 解析出来的 `current_user`。

workspace 解析规则：

- 如果请求带 `workspace_id`，必须属于当前用户。
- 如果请求不带 `workspace_id`，使用当前用户默认 workspace。
- 如果 workspace 不存在或不属于当前用户，返回 `404`。

业务意义：

- 用户只能访问自己的 workspace。
- session 和 run 都必须绑定 workspace。
- 工具执行时只能使用 run 对应 workspace 的 `root_path`。

## SessionRouter

`SessionRouter` 负责把请求路由到正确 session。

规则：

- 不传 `session_id`：创建新 session。
- 传 `session_id`：查询已有 session。
- 已有 session 必须同时满足：
  - `session.user_id == current_user.id`
  - `session.workspace_id == resolved_workspace.id`

这个检查防止两类问题：

- 用户拿别人的 `session_id` 继续对话。
- 把 A workspace 的 session 错接到 B workspace 里执行工具。

## RunRouter

`RunRouter` 负责 run 相关入口规则。

当前规则：

- 同一个 session 同一时间只允许一个 active run。
- active run 包括 `queued`、`running`、`requires_approval`。
- 如果已有 active run，返回 `409`。

创建 run 时必须绑定：

- `user_id`
- `workspace_id`
- `session_id`

这样 Worker 只拿到 `run_id`，也能回数据库恢复完整执行上下文。

## Message 和 Run 的关系

Gateway 当前流程会先保存 user message，再创建 run，然后回填 user message 的 `run_id`。

这样做的原因：

- user message 是一次 chat 请求的原始输入，需要尽早保存。
- run 创建后，message 仍然可以通过 `run_id` 被追踪。
- 后续查某个 run 的 user/assistant 消息会更直接。

## Event Logs

Gateway 阶段写入的事件包括：

| event_type | 说明 |
| --- | --- |
| `chat.request.received` | Gateway 收到 chat 请求 |
| `gateway.auth.checked` | JWT 鉴权已经通过 |
| `workspace.resolved` | 当前请求 workspace 已确认 |
| `session.resolved` | 当前请求 session 已确认 |
| `run.created` | run 已经写入数据库 |
| `run.queued` | run_id 已经投递到 RabbitMQ |

注意：`event_logs.workspace_id` 有外键约束，所以 Gateway 会先解析 workspace，再写 request/auth/workspace 相关事件。

## Worker 边界

Gateway 不执行 Agent。

Gateway 只把 `run_id` 投递到 RabbitMQ：

```text
Gateway -> RabbitMQ -> Worker -> AgentOrchestrator
```

Worker 收到 `run_id` 后，再从数据库读取：

- run
- session
- messages
- workspace
- user

然后进入模型调用和工具调用流程。

## 当前边界

当前已经完成：

- 用户必须登录。
- chat 必须携带 Bearer token。
- workspace 属主检查。
- session 绑定 workspace。
- run 绑定 workspace。
- 工具执行绑定 run 对应 workspace 的 `root_path`。
- `DockerRuntime` 已接入 `run_shell`。
- 前端通过 `GET /api/runs/{run_id}/stream` 使用 SSE 接收真实 LLM streaming 事件。

当前仍需继续收紧：

- Gateway 层更细的事务边界控制。

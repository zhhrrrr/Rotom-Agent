# Event Logs and Model Calls

本文总结 Rotom Agent v1 中 `event_logs` 和 `model_calls` 的记录时机。

## 总览

- `event_logs` 记录一次 run 从 API 接收到请求，到 worker 执行、模型调用、工具调用、最终完成或失败的关键流程节点。
- `model_calls` 记录每一次真实模型请求。只要调用了模型，无论成功还是失败，都会写一条记录。
- 一次 run 可能包含多次模型调用。例如模型第一轮要求调用工具，第二轮根据工具结果生成最终回答，就会写两条 `model_calls`。

## API 阶段的 event_logs

这些记录发生在 `POST /api/chat` 请求处理过程中。

| event_type | 记录时机 | 作用 |
| --- | --- | --- |
| `chat.request.received` | API 收到聊天请求后 | 标记一次用户请求进入系统 |
| `gateway.auth.checked` | 当前默认身份检查完成后 | 为后续真实 User Gateway 预留审计点 |
| `workspace.resolved` | 确定 `workspace_id` 后 | 记录本次请求归属哪个 workspace |
| `session.resolved` | 创建新 session 或找到已有 session 后 | 记录本次请求归属哪个 session |
| `run.created` | 创建 `runs` 记录后 | 记录 run 已入库 |
| `run.queued` | run_id 投递到 RabbitMQ 后 | 记录 run 已进入 worker 队列 |

当前版本还没有真实登录网关；不传 `user_id` 和 `workspace_id` 时，会使用：

- `user_default`
- `workspace_default`

## Worker / Orchestrator 阶段的 event_logs

这些记录发生在 worker 消费 RabbitMQ 消息后，由 `AgentOrchestrator` 写入。

| event_type | 记录时机 | 作用 |
| --- | --- | --- |
| `run.started` | worker 拿到 run 并把状态改为 `running` 后 | 标记后台执行正式开始 |
| `context.built` | `ContextBuilder` 拼好模型上下文后 | 记录发送给模型前的上下文构建完成 |
| `model.call.started` | 每一轮模型调用前 | 标记即将请求模型，并记录 iteration |
| `model.call.completed` | 每一轮模型调用成功后 | 标记模型返回成功，并记录 iteration 和 latency |
| `tool.call.started` | 模型返回 tool_calls 后，每个工具执行前 | 记录即将调用哪个工具和参数 |
| `tool.call.completed` | 每个工具执行结束后 | 记录工具是否执行成功 |
| `run.completed` | 模型给出最终回答、assistant message 保存后 | 标记 run 成功完成 |
| `run.failed` | 超过最大轮数或捕获异常后 | 标记 run 失败，并保存错误信息 |

## model_calls 记录时机

`model_calls` 只记录真实模型请求，不记录 API 请求、工具调用或普通数据库操作。

每次执行：

```python
response = await self.model_client.chat(messages=messages, tools=tools)
```

都会产生一条 `model_calls`。

### 成功时

模型正常返回后，写入一条 `status="completed"` 的 `model_calls`，包含：

- `user_id`
- `workspace_id`
- `session_id`
- `run_id`
- `provider`
- `model`
- `request_messages`
- `request_tools`
- `response_message`
- `prompt_tokens`
- `completion_tokens`
- `latency_ms`
- `status`

### 失败时

模型请求抛异常时，写入一条 `status="failed"` 的 `model_calls`，包含：

- 本次发送给模型的 `request_messages`
- 本次发送给模型的 `request_tools`
- 已经计算出的 `latency_ms`
- `error`

之后异常会继续抛出，由外层把 run 标记为 `failed`，并写入 `event_logs.run.failed`。

## 一次典型工具型 run 的记录顺序

用户发送“请列出当前工作区目录”时，典型顺序如下：

1. `event_logs.chat.request.received`
2. `event_logs.gateway.auth.checked`
3. `event_logs.workspace.resolved`
4. `event_logs.session.resolved`
5. `event_logs.run.created`
6. `event_logs.run.queued`
7. `event_logs.run.started`
8. `event_logs.context.built`
9. `event_logs.model.call.started`
10. `model_calls(status="completed")`
11. `event_logs.model.call.completed`
12. `event_logs.tool.call.started`
13. `tool_calls(status="completed")`
14. `event_logs.tool.call.completed`
15. `event_logs.model.call.started`
16. `model_calls(status="completed")`
17. `event_logs.model.call.completed`
18. 保存 assistant message
19. `event_logs.run.completed`

这里会出现两条 `model_calls`：

- 第一条：模型判断需要调用工具。
- 第二条：模型读取工具结果后生成最终回答。

## 不是 model_calls 的内容

以下内容不会写入 `model_calls`：

- 用户请求进入 API。
- session 创建。
- run 创建。
- RabbitMQ 入队。
- 工具执行详情。
- 最终 assistant message 保存。

这些分别由 `event_logs`、`runs`、`tool_calls`、`messages` 负责记录。

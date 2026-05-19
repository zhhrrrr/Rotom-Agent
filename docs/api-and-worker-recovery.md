# API and Worker Recovery

本文总结 Rotom Agent v1 当前接口和 Worker 恢复机制。

## Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

注册成功会创建默认 workspace，并返回 bearer token。

## Workspaces

- `POST /api/workspaces`
- `GET /api/workspaces`
- `GET /api/workspaces/{workspace_id}`

所有 workspace 接口都需要 JWT，只能访问当前用户自己的 workspace。

## Chat

`POST /api/chat`

请求：

```json
{
  "workspace_id": "ws_xxx",
  "session_id": "sess_xxx",
  "message": "请读取 README.md"
}
```

`workspace_id` 和 `session_id` 可选。不传 workspace 时使用默认 workspace；不传 session 时创建新 session。

返回包含：

```json
{
  "session_id": "sess_xxx",
  "run_id": "run_xxx",
  "status": "queued"
}
```

当前实现还会额外返回 `user_id` 和 `workspace_id`，方便前端直接拿到上下文。

## Run Debug

`GET /api/runs/{run_id}`

返回：

```json
{
  "run": {},
  "messages": [],
  "tool_calls": [],
  "model_calls": [],
  "event_logs": []
}
```

这个接口需要 JWT，并且只能查询当前用户自己的 run。

用途：

- 查看 run 当前状态。
- 查看上下文消息。
- 查看模型真实输入输出。
- 查看工具执行记录。
- 查看 event log 全链路 trace。

## Worker Recovery

Worker 启动时会运行一次恢复扫描：

1. 查询 `status="running"` 的 run。
2. 筛选 `updated_at` 超过 30 分钟未更新的 run。
3. 将这些 run 标记为 `timeout`。
4. 写入 `event_logs.run.timeout`。

v1 暂时不自动重试，先避免 run 永久卡在 `running`。

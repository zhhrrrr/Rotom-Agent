# Rotom Agent 启动命令

本文档记录 v1.5 本地开发时前端、后端、Worker 和基础依赖的启动方式。

## 1. 进入项目根目录

```bash
cd "/home/alpha/projects/v1.5/Rotom Agent"
```

## 2. 启动后端依赖

启动 PostgreSQL、RabbitMQ 等 Docker Compose 中定义的基础服务：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

如果你改了 Dockerfile 或 compose 配置，可以使用：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

## 3. 启动后端 API

新开一个终端：

```bash
cd "/home/alpha/projects/v1.5/Rotom Agent/backend"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端 API 地址：

```text
http://localhost:8000
```

## 4. 启动 Worker

再新开一个终端：

```bash
cd "/home/alpha/projects/v1.5/Rotom Agent/backend"
python worker.py
```

Worker 负责消费 RabbitMQ 中的 run_id，并执行 Agent / LLM / Tool 调用流程。

## 5. 启动前端

再新开一个终端：

```bash
cd "/home/alpha/projects/v1.5/Rotom Agent/frontend"
npm run dev -- --host 0.0.0.0
```

前端页面通常访问：

```text
http://localhost:5174
```

如果 5174 被占用，Vite 会自动换端口，以前端终端输出的 `Local:` 地址为准。

## 6. RabbitMQ 管理页面

RabbitMQ 管理后台通常访问：

```text
http://localhost:15672
```

账号密码以 `deploy/docker-compose.yml` 或 `.env` 中配置为准。

## 7. 推荐启动顺序

1. 启动 Docker Compose 依赖。
2. 启动后端 API。
3. 启动 Worker。
4. 启动前端。
5. 打开前端页面登录或注册后测试聊天。


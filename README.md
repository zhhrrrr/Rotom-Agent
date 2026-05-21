# Rotom Agent

Rotom Agent 是一个带用户、Workspace、RabbitMQ Worker、真实 LLM streaming 和 Vue 前端的工程型 Agent 项目。

## Local setup

1. 复制环境变量模板：

   ```bash
   cp backend/.env.example backend/.env
   ```

2. 填写 `backend/.env`，尤其是 `ZHIPU_API_KEY`。

3. 按顺序启动依赖、后端 API、Worker 和前端：

   ```bash
   docker compose -f deploy/docker-compose.yml up -d
   ```

   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   ```bash
   cd backend
   python worker.py
   ```

   ```bash
   cd frontend
   npm run dev -- --host 0.0.0.0
   ```

4. 检查 API：

   ```bash
   curl http://localhost:8000/health
   ```

完整启动说明见 [docs/startup-commands.md](docs/startup-commands.md)。

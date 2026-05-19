# Rotom Agent

通用 Agent 框架，基于 FastAPI，支持 PostgreSQL 和 RabbitMQ。

## Local setup

1. Copy the example environment file:

   ```bash
   cp backend/.env.example backend/.env
   ```

2. Fill in `backend/.env`, especially `ZHIPU_API_KEY`.

3. Start the services:

   ```bash
   cd deploy
   docker compose up --build
   ```

4. Check the API:

   ```bash
   curl http://localhost:8000/health
   ```

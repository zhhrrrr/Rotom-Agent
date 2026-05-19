# Rotom Agent

Rotom Agent is a FastAPI-based agent service with PostgreSQL and RabbitMQ support.

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

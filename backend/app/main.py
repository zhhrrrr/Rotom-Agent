from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.api import chat_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.database import init_db

setup_logging()

# 把一个异步生成器函数包装成异步上下文管理器
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Rotom Agent", alias="APP_NAME")
    database_url: str = Field(alias="DATABASE_URL")
    rabbitmq_url: str = Field(alias="RABBITMQ_URL")
    rabbitmq_queue: str = Field(alias="RABBITMQ_QUEUE")
    zhipu_api_key: str = Field(alias="ZHIPU_API_KEY")
    zhipu_base_url: str = Field(alias="ZHIPU_BASE_URL")
    zhipu_model: str = Field(alias="ZHIPU_MODEL")
    workspace_root: Path = Field(alias="WORKSPACE_ROOT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

# @lru_cache 把函数的返回结果缓存起来，下次传入相同参数时，不再重新执行函数，而是直接返回缓存结果。
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

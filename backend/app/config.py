from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    database_url: str
    steam_api_key: str
    cors_origins: list[str] = ["http://localhost:3000"]
    steam_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
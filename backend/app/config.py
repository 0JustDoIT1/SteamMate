from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# 실행 위치(CWD)와 무관하게 backend/.env를 읽는다.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    database_url: str
    steam_api_key: str
    # "a,b" 콤마 구분과 '["a","b"]' JSON 배열 모두 허용
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    steam_timeout_seconds: float = 10.0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("["):
            import json

            return json.loads(value)
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

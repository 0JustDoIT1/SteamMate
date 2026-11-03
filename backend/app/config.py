from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
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
    # 세션 쿠키 서명 키. 서버에만 보관하며 32자 이상이어야 한다.
    session_secret: str = Field(min_length=32)
    session_max_age_seconds: int = 7 * 24 * 3600
    # 브라우저가 접속하는 프론트 주소. OpenID realm·return_to와 로그인 후 이동에 쓴다.
    public_base_url: str = "http://localhost:3000"

    # Steam 상점(appdetails) 메타데이터 캐시 — 값은 임시이며 측정 후 조정한다(DEVLOG 3a 참조).
    store_cc: str = "kr"
    store_language: str = "english"
    store_rate_per_second: float = 0.6
    store_burst: int = 10
    store_concurrency: int = 4
    store_rate_limit_pause_seconds: int = 60
    metadata_success_ttl_seconds: int = 7 * 24 * 3600
    metadata_not_available_ttl_seconds: int = 30 * 24 * 3600
    metadata_retry_error_seconds: int = 5 * 60
    metadata_retry_rate_limited_seconds: int = 15 * 60
    metadata_retry_not_found_seconds: int = 60 * 60
    metadata_pending_stale_seconds: int = 10 * 60

    # 대시보드 차트 수집 — 임시값(DEVLOG 3b 참조)
    collector_enabled: bool = True
    collector_run_interval_seconds: int = 3600
    chart_concurrent_interval_seconds: int = 3600
    chart_featured_interval_seconds: int = 6 * 3600
    chart_weekly_interval_seconds: int = 6 * 3600
    chart_retention_days: int = 14
    # 판매 순위는 월간·연간 집계를 위해 1년+1주 보관(집계 주 기준)
    chart_weekly_retention_weeks: int = 53
    # 보유 게임 목록 메모리 캐시(저장하지 않음)
    owned_cache_ttl_seconds: int = 300
    # 장르 수집률이 이 값 이상이면 GENRE_AWARE, 미만이면 PLAYTIME_BASED — PRD 임시 가정 90%
    recommendation_genre_threshold: float = 0.9
    # 가격 캐시(game_price) — 임시값(DEVLOG 5단계 참조)
    price_ttl_seconds: int = 3600
    price_retry_error_seconds: int = 5 * 60
    price_retry_not_found_seconds: int = 3600
    # 사용자 요청 한 번에 받는 가격 묶음(100개) 수. 나머지는 화면 폴링이 이어 받는다.
    price_max_batches_per_request: int = 3

    @property
    def cookie_secure(self) -> bool:
        return self.app_env not in ("local", "test")

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

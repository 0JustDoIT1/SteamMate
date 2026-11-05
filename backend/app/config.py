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
    # 뉴스 발췌 메모리 캐시(본문 전문은 캐시하지 않음)
    news_cache_seconds: int = 600

    # 뉴스 AI 질문(F6 R2, PRD v6.7). 권리 확인 전 공개 배포는 OFF — 로컬 .env에서만 켠다.
    news_ai_enabled: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    qa_model: str = "bonsai-2:9b"
    qa_embed_model: str = "bge-m3"
    qa_timeout_seconds: float = 120.0
    qa_num_predict: int = 1024  # 7단계 실험과 같은 값
    qa_max_docs: int = 50
    # 정제 후 코퍼스가 이 토큰 수 이하면 Full Context, 넘으면 RAG(7단계 실험, bonsai-2:9b 기준)
    qa_full_context_max_tokens: int = 8000
    # 토큰 어림값. 실험 데이터는 3.25~3.6자/토큰 → 3으로 잡아 토큰을 넉넉히(Full Context를 덜) 센다.
    qa_chars_per_token: float = 3.0
    qa_top_k: int = 5
    # 최신 업데이트 공지에서 질문과 가까운 청크를 이만큼 더 넣는다(RAG)
    qa_pinned_chunks: int = 3
    # Top-K + 고정 청크(최대 8개 x 약 1,200자, 한국어는 토큰이 더 많음)가 잘리지 않게
    qa_rag_num_ctx: int = 12_288
    # 질문용 코퍼스(정리한 전문·임베딩) 메모리 캐시. 영구 저장하지 않는다.
    qa_cache_seconds: int = 600

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

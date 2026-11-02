from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth.session import SessionManager
from app.auth.steam_openid import NonceStore
from app.config import Settings, get_settings
from app.db import dispose_engine, get_engine, get_sessionmaker
from app.errors import register_error_handlers
from app.infra.rate_limit import TokenBucket
from app.logging_config import configure_logging
from app.metadata.service import MetadataLookup, MetadataService
from app.metadata.state import MetadataPolicy
from app.routers import auth, me
from app.steam.store_api import StoreApi


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(secrets=(settings.steam_api_key, settings.session_secret))
    metadata = app.state.metadata
    if isinstance(metadata, MetadataService):
        metadata.start()
    yield
    if isinstance(metadata, MetadataService):
        await metadata.stop()
    await app.state.http.aclose()
    await dispose_engine()


def build_metadata_service(settings: Settings, http: httpx.AsyncClient) -> MetadataService:
    return MetadataService(
        get_sessionmaker,
        StoreApi(http, cc=settings.store_cc, language=settings.store_language),
        TokenBucket(settings.store_rate_per_second, settings.store_burst),
        MetadataPolicy(
            success_ttl=timedelta(seconds=settings.metadata_success_ttl_seconds),
            not_available_ttl=timedelta(seconds=settings.metadata_not_available_ttl_seconds),
            retry_error=timedelta(seconds=settings.metadata_retry_error_seconds),
            retry_rate_limited=timedelta(seconds=settings.metadata_retry_rate_limited_seconds),
            retry_not_found=timedelta(seconds=settings.metadata_retry_not_found_seconds),
            pending_stale=timedelta(seconds=settings.metadata_pending_stale_seconds),
        ),
        concurrency=settings.store_concurrency,
        rate_limit_pause_seconds=settings.store_rate_limit_pause_seconds,
    )


def create_app(http: httpx.AsyncClient | None = None, metadata: MetadataLookup | None = None) -> FastAPI:
    """http: 외부 API용 클라이언트, metadata: 메타데이터 캐시. 테스트에서는 가짜를 주입한다."""
    settings = get_settings()
    app = FastAPI(title="SteamMate API", lifespan=lifespan)

    app.state.http = http or httpx.AsyncClient(timeout=settings.steam_timeout_seconds)
    app.state.sessions = SessionManager(settings.session_secret, settings.session_max_age_seconds)
    app.state.nonces = NonceStore()
    app.state.metadata = metadata or build_metadata_service(settings, app.state.http)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(me.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "env": settings.app_env}

    @app.get("/health/db")
    async def health_db():
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"db": "ok"}

    return app


app = create_app()

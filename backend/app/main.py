import asyncio
import contextlib
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
from app.dashboard import DashboardService
from app.db import dispose_engine, get_engine, get_sessionmaker
from app.errors import register_error_handlers
from app.infra.rate_limit import TokenBucket
from app.jobs.collector import Collector, CollectorPolicy, run_periodically
from app.logging_config import configure_logging
from app.metadata.service import MetadataLookup, MetadataService
from app.metadata.state import MetadataPolicy
from app.models import ChartSource
from app.owned_cache import OwnedGamesCache
from app.routers import auth, dashboard, me
from app.steam.charts_api import ChartsApi
from app.steam.store_api import StoreApi


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(secrets=(settings.steam_api_key, settings.session_secret))
    metadata = app.state.metadata
    collector_task = None
    if isinstance(metadata, MetadataService):
        metadata.start()
        if settings.collector_enabled:
            collector = build_collector(settings, app.state.http, metadata)
            interval = timedelta(seconds=settings.collector_run_interval_seconds)
            collector_task = asyncio.create_task(run_periodically(collector, interval))
    yield
    if collector_task:
        collector_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await collector_task
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


def build_collector(settings: Settings, http: httpx.AsyncClient, metadata: MetadataLookup) -> Collector:
    weekly = timedelta(seconds=settings.chart_weekly_interval_seconds)
    featured = timedelta(seconds=settings.chart_featured_interval_seconds)
    return Collector(
        get_sessionmaker,
        ChartsApi(http, settings.steam_api_key, cc=settings.store_cc, language=settings.store_language),
        metadata,
        CollectorPolicy(
            intervals={
                ChartSource.TOP_SELLERS: weekly,
                ChartSource.MOST_PLAYED: weekly,
                ChartSource.CONCURRENT: timedelta(seconds=settings.chart_concurrent_interval_seconds),
                ChartSource.SPECIALS: featured,
                ChartSource.NEW_RELEASES: featured,
            },
            retention={
                ChartSource.TOP_SELLERS: timedelta(weeks=settings.chart_weekly_retention_weeks),
                ChartSource.MOST_PLAYED: timedelta(days=settings.chart_retention_days),
                ChartSource.CONCURRENT: timedelta(days=settings.chart_retention_days),
                ChartSource.SPECIALS: timedelta(days=settings.chart_retention_days),
                ChartSource.NEW_RELEASES: timedelta(days=settings.chart_retention_days),
            },
        ),
        cc=settings.store_cc,
    )


def create_app(
    http: httpx.AsyncClient | None = None,
    metadata: MetadataLookup | None = None,
    dashboard_service: DashboardService | None = None,
) -> FastAPI:
    """http·metadata·dashboard_service: 테스트에서 가짜를 주입한다(기본은 실제 구현)."""
    settings = get_settings()
    app = FastAPI(title="SteamMate API", lifespan=lifespan)

    app.state.http = http or httpx.AsyncClient(timeout=settings.steam_timeout_seconds)
    app.state.sessions = SessionManager(settings.session_secret, settings.session_max_age_seconds)
    app.state.nonces = NonceStore()
    app.state.owned = OwnedGamesCache(settings.owned_cache_ttl_seconds)
    app.state.metadata = metadata or build_metadata_service(settings, app.state.http)
    app.state.dashboard = dashboard_service or DashboardService(
        get_sessionmaker, app.state.metadata, cc=settings.store_cc
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(dashboard.router)

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

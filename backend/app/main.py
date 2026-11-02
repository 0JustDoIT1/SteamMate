from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth.session import SessionManager
from app.auth.steam_openid import NonceStore
from app.config import get_settings
from app.db import dispose_engine, get_engine
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.routers import auth, me


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(secrets=(settings.steam_api_key, settings.session_secret))
    yield
    await app.state.http.aclose()
    await dispose_engine()


def create_app(http: httpx.AsyncClient | None = None) -> FastAPI:
    """http: 외부 API용 클라이언트. 테스트에서는 MockTransport 클라이언트를 주입한다."""
    settings = get_settings()
    app = FastAPI(title="SteamMate API", lifespan=lifespan)

    app.state.http = http or httpx.AsyncClient(timeout=settings.steam_timeout_seconds)
    app.state.sessions = SessionManager(settings.session_secret, settings.session_max_age_seconds)
    app.state.nonces = NonceStore()

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

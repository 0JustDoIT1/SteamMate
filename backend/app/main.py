from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import dispose_engine, get_engine
from app.errors import register_error_handlers
from app.logging_config import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(secrets=(get_settings().steam_api_key,))
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SteamMate API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)

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

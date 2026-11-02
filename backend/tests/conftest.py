import os
from collections.abc import AsyncIterator

import httpx
import pytest

# 테스트는 로컬 backend/.env와 무관하게 동작해야 한다. 앱 import 전에 환경을 고정한다.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or "postgresql+asyncpg://test:test@localhost:1/test"
os.environ["STEAM_API_KEY"] = "test-steam-key-0123456789"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["APP_ENV"] = "test"

from app.config import get_settings
from app.db import dispose_engine


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    skip_db = pytest.mark.skip(reason="TEST_DATABASE_URL 미설정: DB 테스트는 CI 또는 로컬 DB에서 실행")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await dispose_engine()

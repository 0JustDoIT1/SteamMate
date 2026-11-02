import json
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

# 테스트는 로컬 backend/.env와 무관하게 동작해야 한다. 앱 import 전에 환경을 고정한다.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or "postgresql+asyncpg://test:test@localhost:1/test"
os.environ["STEAM_API_KEY"] = "test-steam-key-0123456789"
os.environ["SESSION_SECRET"] = "test-session-secret-0123456789abcdef"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:3000"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["APP_ENV"] = "test"

from app.config import get_settings
from app.db import dispose_engine

FIXTURES = Path(__file__).parent / "fixtures"
TEST_STEAM_ID = "76561198000000001"  # 실제 계정이 아닌 테스트용 값

Handler = Callable[[httpx.Request], httpx.Response]


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    skip_db = pytest.mark.skip(reason="TEST_DATABASE_URL 미설정: DB 테스트는 CI 또는 로컬 DB에서 실행")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"예상하지 못한 외부 호출: {request.method} {request.url.host}{request.url.path}")


@pytest.fixture
def steam_handler() -> dict[str, Handler]:
    """테스트에서 외부 응답을 지정한다: steam_handler['fn'] = handler"""
    return {"fn": _no_network}


@pytest.fixture
async def client(steam_handler) -> AsyncIterator[httpx.AsyncClient]:
    get_settings.cache_clear()
    from app.main import create_app

    external = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: steam_handler["fn"](r)))
    app = create_app(http=external)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.app = app  # 테스트에서 세션 발급 등에 사용
        yield ac
    await external.aclose()
    await dispose_engine()


@pytest.fixture
def login(client) -> Callable[[str], None]:
    """유효한 세션 쿠키를 심는다."""

    def _login(steam_id: str = TEST_STEAM_ID) -> None:
        client.cookies.set("sm_session", client.app.state.sessions.issue(steam_id))

    return _login

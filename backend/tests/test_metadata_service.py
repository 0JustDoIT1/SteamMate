"""실제 PostgreSQL(마이그레이션 적용)에서 보강 서비스 전체 흐름을 검증한다."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.infra.rate_limit import TokenBucket
from app.metadata.service import MetadataService
from app.metadata.state import MetadataPolicy
from app.models import FetchStatus, GameMetadata
from app.steam.store_api import StoreApi

pytestmark = pytest.mark.db

POLICY = MetadataPolicy(
    success_ttl=timedelta(days=7),
    not_available_ttl=timedelta(days=30),
    retry_error=timedelta(minutes=5),
    retry_rate_limited=timedelta(minutes=15),
    retry_not_found=timedelta(hours=1),
    pending_stale=timedelta(minutes=10),
)


def details(appid: int, genres: list[str] | None = None, app_type: str = "game") -> dict:
    data = {"type": app_type, "name": f"Game {appid}"}
    if genres:
        data["genres"] = [{"id": str(i), "description": g} for i, g in enumerate(genres)]
    return {str(appid): {"success": True, "data": data}}


class StoreStub:
    """appid별 응답을 지정하고 호출 횟수를 센다."""

    def __init__(self, responses: dict[int, httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[int] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        appid = int(request.url.params["appids"])
        self.calls.append(appid)
        return self.responses[appid]


@pytest.fixture
async def make_service(db_sessionmaker):
    """서비스를 만들고 워커를 시작한다. 테스트가 끝나면 워커를 정지한다."""
    services: list[MetadataService] = []

    def _make(stub: StoreStub, limiter: TokenBucket | None = None, now=None) -> MetadataService:
        http = httpx.AsyncClient(transport=httpx.MockTransport(stub.handler))
        svc = MetadataService(
            lambda: db_sessionmaker,
            StoreApi(http, cc="kr", language="english"),
            limiter or TokenBucket(1000, 1000),
            POLICY,
            concurrency=4,
            rate_limit_pause_seconds=60,
            **({"now": now} if now else {}),
        )
        svc.start()
        services.append(svc)
        return svc

    yield _make
    for svc in services:
        await svc.stop()


async def rows(sm) -> dict[int, GameMetadata]:
    async with sm() as session:
        return {r.appid: r for r in await session.scalars(select(GameMetadata))}


async def test_lookup_returns_immediately_then_enriches_in_background(make_service, db_sessionmaker):
    stub = StoreStub({620: httpx.Response(200, json=details(620, ["Action", "Adventure"]))})
    svc = make_service(stub)

    first = await svc.lookup([620])
    assert first[620].status is FetchStatus.PENDING  # 기다리지 않고 부분 응답

    await svc.drain()
    second = await svc.lookup([620])
    assert second[620].status is FetchStatus.SUCCESS
    assert second[620].genres == ("Action", "Adventure")
    assert stub.calls == [620]  # 캐시 적중: 두 번째 lookup은 Steam을 부르지 않는다


async def test_concurrent_lookups_fetch_each_game_once(make_service):
    stub = StoreStub({a: httpx.Response(200, json=details(a, ["RPG"])) for a in (1, 2, 3)})
    svc = make_service(stub)

    await asyncio.gather(*(svc.lookup([1, 2, 3]) for _ in range(5)))
    await svc.drain()

    assert sorted(stub.calls) == [1, 2, 3]


async def test_rate_limit_marks_temporary_and_pauses_limiter(make_service, db_sessionmaker):
    stub = StoreStub({7: httpx.Response(429)})
    limiter = TokenBucket(1000, 1000)
    svc = make_service(stub, limiter)

    await svc.lookup([7])
    await svc.drain()

    row = (await rows(db_sessionmaker))[7]
    assert row.fetch_status is FetchStatus.TEMPORARY_ERROR
    assert row.failure_reason == "rate_limited"
    assert limiter._paused_until > 0


async def test_no_genres_is_not_available_and_not_refetched(make_service, db_sessionmaker):
    stub = StoreStub({9: httpx.Response(200, json=details(9, None, app_type="music"))})
    svc = make_service(stub)

    await svc.lookup([9])
    await svc.drain()
    snap = (await svc.lookup([9]))[9]

    assert snap.status is FetchStatus.NOT_AVAILABLE and snap.app_type == "music"
    assert stub.calls == [9]


async def test_success_false_twice_confirms_not_available(make_service, db_sessionmaker):
    stub = StoreStub({11: httpx.Response(200, json={"11": {"success": False}})})
    clock = {"now": datetime(2026, 11, 3, tzinfo=UTC)}
    svc = make_service(stub, now=lambda: clock["now"])

    await svc.lookup([11])
    await svc.drain()
    assert (await rows(db_sessionmaker))[11].fetch_status is FetchStatus.TEMPORARY_ERROR

    clock["now"] += timedelta(hours=1)  # retry_after 경과
    await svc.lookup([11])
    await svc.drain()
    assert (await rows(db_sessionmaker))[11].fetch_status is FetchStatus.NOT_AVAILABLE
    assert stub.calls == [11, 11]


async def test_stale_pending_is_recovered(make_service, db_sessionmaker):
    """서버 재시작으로 대기열이 사라져 PENDING으로 남은 행을 다시 처리한다."""
    old = datetime(2026, 11, 3, tzinfo=UTC)
    async with db_sessionmaker() as session:
        session.add(GameMetadata(appid=13, fetch_status=FetchStatus.PENDING, last_checked_at=old))
        await session.commit()

    stub = StoreStub({13: httpx.Response(200, json=details(13, ["Indie"]))})
    svc = make_service(stub, now=lambda: old + timedelta(minutes=11))
    await svc.lookup([13])
    await svc.drain()

    assert (await rows(db_sessionmaker))[13].fetch_status is FetchStatus.SUCCESS


async def test_fresh_pending_is_not_duplicated(make_service, db_sessionmaker):
    now = datetime(2026, 11, 3, tzinfo=UTC)
    async with db_sessionmaker() as session:
        session.add(GameMetadata(appid=15, fetch_status=FetchStatus.PENDING, last_checked_at=now))
        await session.commit()

    stub = StoreStub({})
    svc = make_service(stub, now=lambda: now + timedelta(minutes=1))
    await svc.lookup([15])
    await svc.drain()
    assert stub.calls == []  # 다른 워커가 처리 중일 수 있으므로 건드리지 않는다


async def test_expired_success_keeps_genres_when_refresh_fails(make_service, db_sessionmaker):
    t0 = datetime(2026, 11, 3, tzinfo=UTC)
    async with db_sessionmaker() as session:
        session.add(
            GameMetadata(
                appid=17,
                fetch_status=FetchStatus.SUCCESS,
                genres_json=[{"id": "1", "description": "Action"}],
                fetched_at=t0,
                expires_at=t0 + timedelta(days=7),
            )
        )
        await session.commit()

    stub = StoreStub({17: httpx.Response(503)})
    svc = make_service(stub, now=lambda: t0 + timedelta(days=8))
    stale = await svc.lookup([17])
    assert stale[17].status is FetchStatus.SUCCESS  # 갱신 중에도 기존 데이터를 보여준다
    await svc.drain()

    row = (await rows(db_sessionmaker))[17]
    assert row.fetch_status is FetchStatus.SUCCESS
    assert row.genres_json == [{"id": "1", "description": "Action"}]
    assert row.expires_at == t0 + timedelta(days=8, minutes=5)


async def test_worker_survives_unexpected_error(make_service, db_sessionmaker):
    stub = StoreStub({21: httpx.Response(200, json=details(21, ["RPG"]))})
    svc = make_service(stub)
    original = svc._refresh
    calls = {"n": 0}

    async def flaky(appid: int) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        await original(appid)

    svc._refresh = flaky
    await svc.lookup([21])
    await svc.drain()
    # 첫 시도 실패 후에도 워커가 살아 있어 다음 요청을 처리한다
    async with db_sessionmaker() as session:
        await session.execute(
            update(GameMetadata).where(GameMetadata.appid == 21).values(last_checked_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
        await session.commit()
    await svc.lookup([21])
    await svc.drain()
    assert (await rows(db_sessionmaker))[21].fetch_status is FetchStatus.SUCCESS

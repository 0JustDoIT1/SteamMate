"""실제 PostgreSQL에서 가격 캐시(game_price)의 묶음 조회·상태 전이·만료를 검증한다."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.infra.rate_limit import TokenBucket
from app.models import FetchStatus, GamePrice
from app.prices import PricePolicy, PriceService, price_info
from app.steam.store_api import StoreApi

pytestmark = pytest.mark.db

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
POLICY = PricePolicy(
    ttl=timedelta(hours=1),
    retry_error=timedelta(minutes=5),
    retry_rate_limited=timedelta(minutes=15),
    retry_not_found=timedelta(hours=1),
)


def priced(initial: int, final: int, discount: int) -> dict:
    return {
        "success": True,
        "data": {
            "price_overview": {
                "currency": "KRW", "initial": initial, "final": final, "discount_percent": discount,
                "initial_formatted": "", "final_formatted": "",
            }
        },
    }


FREE = {"success": True, "data": []}  # 무료·미출시: 가격 없이 빈 배열
MISSING = {"success": False}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class PriceStub:
    """요청된 appid 목록을 기록하고 appid별 응답을 돌려준다. status를 바꾸면 요청 전체가 그 상태로 실패한다."""

    def __init__(self, entries: dict[int, dict] | None = None, default: dict | None = None) -> None:
        self.entries = entries or {}
        self.default = default or priced(1000, 1000, 0)
        self.status = 200
        self.batches: list[list[int]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.params["filters"] == "price_overview"
        ids = [int(a) for a in request.url.params["appids"].split(",")]
        self.batches.append(ids)
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, json={str(a): self.entries.get(a, self.default) for a in ids})


def make(db_sessionmaker, stub: PriceStub, clock: Clock, batch_size: int = 100) -> PriceService:
    http = httpx.AsyncClient(transport=httpx.MockTransport(stub.handler))
    return PriceService(
        lambda: db_sessionmaker,
        StoreApi(http, cc="kr", language="english"),
        TokenBucket(1000, 1000),
        POLICY,
        cc="kr",
        rate_limit_pause_seconds=0.01,  # 실제 시간으로 멈추므로 테스트에서는 짧게
        batch_size=batch_size,
        now=clock,
    )


async def test_fetches_in_one_batch_and_maps_states(db_sessionmaker):
    stub = PriceStub({1: priced(2000, 1000, 50), 2: FREE, 3: MISSING})
    svc = make(db_sessionmaker, stub, Clock(T0))

    got = await svc.lookup([3, 1, 2, 1])

    assert stub.batches == [[1, 2, 3]]
    assert got[1].status is FetchStatus.SUCCESS and got[1].on_sale and got[1].final_price == 1000
    assert price_info(got[1]).discount_percent == 50
    # 가격 없는 정상 응답은 SUCCESS + 가격 없음(무료·미출시를 구분하지 않는다)
    assert got[2].status is FetchStatus.SUCCESS and not got[2].has_price and price_info(got[2]) is None
    assert got[3].status is FetchStatus.NOT_AVAILABLE


async def test_cached_until_ttl_then_refetched(db_sessionmaker):
    stub = PriceStub()
    clock = Clock(T0)
    svc = make(db_sessionmaker, stub, clock)

    await svc.lookup([1])
    await svc.lookup([1])
    assert len(stub.batches) == 1  # 1시간 안에는 다시 묻지 않는다

    clock.now = T0 + timedelta(hours=1)
    stub.default = priced(1000, 500, 50)
    got = await svc.lookup([1])
    assert len(stub.batches) == 2 and got[1].final_price == 500


async def test_max_batches_leaves_rest_pending_for_next_request(db_sessionmaker):
    stub = PriceStub()
    svc = make(db_sessionmaker, stub, Clock(T0), batch_size=2)

    first = await svc.lookup(range(1, 6), max_batches=1)
    assert stub.batches == [[1, 2]]
    assert [first[a].status for a in range(1, 6)] == [FetchStatus.SUCCESS] * 2 + [FetchStatus.PENDING] * 3

    second = await svc.lookup(range(1, 6), max_batches=1)
    assert stub.batches[-1] == [3, 4]  # 이미 받은 게임은 건너뛰고 이어서 받는다
    assert second[5].status is FetchStatus.PENDING


@pytest.mark.parametrize("status", [500, 429])
async def test_request_failure_is_temporary_not_missing(db_sessionmaker, status):
    stub = PriceStub()
    stub.status = status
    clock = Clock(T0)
    svc = make(db_sessionmaker, stub, clock)

    got = await svc.lookup([1])

    assert got[1].status is FetchStatus.TEMPORARY_ERROR
    await svc.lookup([1])
    assert len(stub.batches) == 1  # 재시도 시각 전에는 다시 묻지 않는다
    clock.now = T0 + timedelta(minutes=15)
    stub.status = 200
    assert (await svc.lookup([1]))[1].status is FetchStatus.SUCCESS


async def test_failure_keeps_previous_price(db_sessionmaker):
    stub = PriceStub(default=priced(2000, 1000, 50))
    clock = Clock(T0)
    svc = make(db_sessionmaker, stub, clock)
    await svc.lookup([1])

    clock.now = T0 + timedelta(hours=2)
    stub.status = 500
    got = await svc.lookup([1])

    assert got[1].status is FetchStatus.SUCCESS and got[1].final_price == 1000
    async with db_sessionmaker() as s:
        row = await s.scalar(select(GamePrice).where(GamePrice.appid == 1))
    assert row.failure_reason == "http_500" and row.expires_at == clock.now + POLICY.retry_error


async def test_rate_limit_stops_remaining_batches(db_sessionmaker):
    stub = PriceStub()
    stub.status = 429
    svc = make(db_sessionmaker, stub, Clock(T0), batch_size=2)

    got = await svc.lookup(range(1, 6))

    assert len(stub.batches) == 1  # 제한이 걸리면 남은 묶음을 보내지 않는다
    assert got[1].status is FetchStatus.TEMPORARY_ERROR and got[3].status is FetchStatus.PENDING


async def test_schema_mismatch_is_temporary(db_sessionmaker):
    stub = PriceStub({1: {"success": True, "data": {"price_overview": {"currency": "KRW"}}}})
    svc = make(db_sessionmaker, stub, Clock(T0))
    got = await svc.lookup([1, 2])
    assert got[1].status is FetchStatus.TEMPORARY_ERROR
    assert got[2].status is FetchStatus.SUCCESS

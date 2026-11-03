"""실제 PostgreSQL에서 차트 수집 작업을 검증한다."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text

from app.jobs.collector import BACKFILL_WEEKS, LOCK_KEY, Collector, CollectorPolicy
from app.metadata.service import Priority
from app.models import ChartEntry, ChartSnapshot, ChartSource, SnapshotStatus
from app.steam.charts_api import ChartsApi
from tests.fakes import FakeMetadata, FakePrices
from tests.fixtures.steam.charts import TOP_SELLERS
from tests.test_charts_api import PATHS

pytestmark = pytest.mark.db

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
TOP_SELLERS_PATH = "/IStoreTopSellersService/GetWeeklyTopSellers/v1/"
CURRENT_WEEK = TOP_SELLERS["response"]["start_date"]
POLICY = CollectorPolicy(
    intervals={
        ChartSource.TOP_SELLERS: timedelta(hours=6),
        ChartSource.MOST_PLAYED: timedelta(hours=6),
        ChartSource.CONCURRENT: timedelta(hours=1),
        ChartSource.SPECIALS: timedelta(hours=6),
        ChartSource.NEW_RELEASES: timedelta(hours=6),
    },
    retention={
        ChartSource.TOP_SELLERS: timedelta(weeks=53),
        ChartSource.MOST_PLAYED: timedelta(days=14),
        ChartSource.CONCURRENT: timedelta(days=14),
        ChartSource.SPECIALS: timedelta(days=14),
        ChartSource.NEW_RELEASES: timedelta(days=14),
    },
)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def top_sellers_for(request: httpx.Request, history: bool) -> dict:
    """Steam처럼 요청한 주(start_date)의 순위를 돌려준다. history=False면 항상 현재 주."""
    body = copy.deepcopy(TOP_SELLERS)
    requested = json.loads(request.url.params["input_json"]).get("start_date")
    if history and requested:
        body["response"]["start_date"] = requested
        weeks_ago = (CURRENT_WEEK - requested) // (7 * 86400)
        for r in body["response"]["ranks"]:  # 주마다 순위가 조금씩 다르게
            r["rank"] = 1 + (r["rank"] - 1 + weeks_ago) % 3
    return body


def make_collector(
    db_sessionmaker,
    clock: Clock,
    metadata=None,
    overrides: dict | None = None,
    calls: list | None = None,
    history: bool = False,
    prices=None,
):
    responses = {**PATHS, **(overrides or {})}

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        r = responses[request.url.path]
        if request.url.path == TOP_SELLERS_PATH and not isinstance(r, httpx.Response):
            r = top_sellers_for(request, history)
        return r if isinstance(r, httpx.Response) else httpx.Response(200, json=r)

    charts = ChartsApi(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "k", "kr", "english")
    return Collector(
        lambda: db_sessionmaker, charts, metadata or FakeMetadata(), POLICY, cc="kr", now=clock, prices=prices
    )


async def snapshots(sm, source: ChartSource | None = None) -> list[ChartSnapshot]:
    async with sm() as s:
        q = select(ChartSnapshot).order_by(ChartSnapshot.id)
        if source:
            q = q.where(ChartSnapshot.source == source)
        return list(await s.scalars(q))


async def test_first_run_stores_all_sources_and_requests_metadata_low_priority(db_sessionmaker):
    meta = FakeMetadata()
    report = await make_collector(db_sessionmaker, Clock(T0), meta).run_once()

    assert report.ran and sorted(report.stored) == sorted(ChartSource)
    snaps = await snapshots(db_sessionmaker)
    assert {s.source for s in snaps} == set(ChartSource)
    assert all(s.status is SnapshotStatus.SUCCESS for s in snaps)
    async with db_sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(ChartEntry)) == 3 + 2 + 2 + 2 + 1
    assert set(meta.requested[0]) == {730, 570, 999001, 440, 578080, 620, 1091500, 999002}
    assert meta.priorities == [Priority.LOW]  # 수집 작업은 사용자 요청보다 뒤로


async def test_top_sellers_backfills_past_weeks_once(db_sessionmaker):
    clock = Clock(T0)
    collector = make_collector(db_sessionmaker, clock, history=True)

    report = await collector.run_once()

    # 기준 주에서 1~51주 전 중 보관 기간(지금부터 53주) 안에 드는 주만 채운다
    anchor = datetime.fromtimestamp(CURRENT_WEEK, UTC)
    keep_since = T0 - POLICY.retention[ChartSource.TOP_SELLERS]
    expected = [k for k in range(1, BACKFILL_WEEKS) if anchor - timedelta(weeks=k) >= keep_since]
    assert report.backfilled == len(expected) >= 50
    periods = sorted(s.period_start for s in await snapshots(db_sessionmaker, ChartSource.TOP_SELLERS))
    assert len(periods) == len(expected) + 1
    assert periods[0] == anchor - timedelta(weeks=max(expected))

    clock.now = T0 + timedelta(hours=6)
    again = await collector.run_once()
    assert again.backfilled == 0  # 이미 채운 주는 다시 받지 않는다


async def test_backfill_runs_only_when_top_sellers_due(db_sessionmaker):
    clock = Clock(T0)
    calls: list = []
    collector = make_collector(db_sessionmaker, clock, calls=calls)  # history=False: 과거 주를 못 받는 상황
    await collector.run_once()
    calls.clear()

    clock.now = T0 + timedelta(hours=1)  # 동시 접속만 간격 경과
    report = await collector.run_once()

    assert report.stored == [ChartSource.CONCURRENT]
    assert calls == ["/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"]  # 백필 재요청 없음


async def test_same_weekly_period_is_not_stored_again(db_sessionmaker):
    clock = Clock(T0)
    collector = make_collector(db_sessionmaker, clock)
    await collector.run_once()

    clock.now = T0 + timedelta(hours=6)
    report = await collector.run_once()

    assert ChartSource.TOP_SELLERS in report.skipped and ChartSource.MOST_PLAYED in report.skipped
    sources = [s.source for s in await snapshots(db_sessionmaker)]
    assert sources.count(ChartSource.TOP_SELLERS) == 1
    assert sources.count(ChartSource.SPECIALS) == 2  # 기획 목록은 주기마다 새로 저장


async def test_failure_is_recorded_and_retried_next_run(db_sessionmaker):
    clock = Clock(T0)
    bad = {"/ISteamChartsService/GetMostPlayedGames/v1/": httpx.Response(503)}
    await make_collector(db_sessionmaker, clock, overrides=bad).run_once()

    failed = await snapshots(db_sessionmaker, ChartSource.MOST_PLAYED)
    assert [(s.status, s.failure_reason) for s in failed] == [(SnapshotStatus.FAILED, "http_503")]

    clock.now = T0 + timedelta(minutes=5)  # 성공본이 없으므로 간격과 무관하게 다시 시도
    report = await make_collector(db_sessionmaker, clock).run_once()
    assert ChartSource.MOST_PLAYED in report.stored


async def test_advisory_lock_allows_one_run_at_a_time(db_sessionmaker):
    collector = make_collector(db_sessionmaker, Clock(T0))
    async with db_sessionmaker() as holder, holder.begin():
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
        report = await collector.run_once()  # 다른 연결이 잠금을 쥐고 있음
        assert report.ran is False
    assert (await collector.run_once()).ran is True  # 잠금 해제 후에는 실행


async def test_concurrent_runs_do_not_duplicate(db_sessionmaker):
    collectors = [make_collector(db_sessionmaker, Clock(T0)) for _ in range(3)]
    reports = await asyncio.gather(*(c.run_once() for c in collectors))
    stored = [src for r in reports for src in r.stored]
    assert sorted(stored) == sorted(ChartSource)  # 소스마다 한 번만 저장


async def test_retention_uses_period_for_weekly_and_keeps_latest_success(db_sessionmaker):
    clock = Clock(T0)
    await make_collector(db_sessionmaker, clock, history=True).run_once()

    clock.now = T0 + timedelta(days=15)
    bad = {"/ISteamChartsService/GetGamesByConcurrentPlayers/v1/": httpx.Response(503)}
    await make_collector(db_sessionmaker, clock, overrides=bad).run_once()

    # 비주간: 14일 지난 성공본은 삭제되지만, 유일한 성공본이면 남는다
    concurrent = await snapshots(db_sessionmaker, ChartSource.CONCURRENT)
    assert [s.status for s in concurrent] == [SnapshotStatus.SUCCESS, SnapshotStatus.FAILED]
    specials = await snapshots(db_sessionmaker, ChartSource.SPECIALS)
    assert len(specials) == 1 and specials[0].captured_at == clock.now

    # 주간: 백필로 오늘 수집했어도 집계 주가 53주보다 오래된 것은 삭제 대상
    clock.now = T0 + timedelta(weeks=3)
    await make_collector(db_sessionmaker, clock, history=True).run_once()
    oldest = min(s.period_start for s in await snapshots(db_sessionmaker, ChartSource.TOP_SELLERS))
    assert oldest >= clock.now - timedelta(weeks=53)


async def test_prefetches_candidate_pool_prices(db_sessionmaker):
    prices = FakePrices()
    await make_collector(db_sessionmaker, Clock(T0), prices=prices).run_once()

    # 방금 수집한 목록 전체(후보 풀)의 가격을 묶음 제한 없이 미리 받는다
    ids, max_batches = prices.requested[0]
    assert set(ids) == {730, 570, 999001, 440, 578080, 620, 1091500, 999002} and max_batches is None

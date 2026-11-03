"""인기 대시보드. 소스별 최신 SUCCESS 스냅샷을 읽고, 주간 차트는 월간·연간 합산 순위를 함께 만든다.

- 공개 부분(순위·장르)은 짧게 메모리 캐시하고, 로그인 시 보유 여부·취향 매칭도를 덧붙인다.
- 월간·연간은 Steam 공식 순위가 아니라 주간 순위를 합산한 값이다(주마다 101 − 순위점).
- 개인화에 쓰는 보유 목록은 요청 단위로만 사용하고 저장하지 않는다.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.chart_queries import latest_success_ids
from app.errors import AppError, ErrorCode
from app.genre_labels import korean_genre, korean_genres
from app.metadata.service import MetadataLookup, MetadataSnapshot, Priority
from app.models import (
    ChartEntry,
    ChartSnapshot,
    ChartSource,
    FetchStatus,
    SnapshotStatus,
)
from app.owned_cache import OwnedGamesCache
from app.schemas import CamelModel
from app.steam.web_api import SteamWebApi
from app.taste import affinity, genre_preference

logger = logging.getLogger(__name__)

SECTION_ORDER = [
    ChartSource.TOP_SELLERS,
    ChartSource.MOST_PLAYED,
    ChartSource.CONCURRENT,
    ChartSource.SPECIALS,
    ChartSource.NEW_RELEASES,
]
WEEKLY = (ChartSource.TOP_SELLERS, ChartSource.MOST_PLAYED)  # 지난주 순위(순위 변화)가 있는 주간 차트
# 월간·연간 합산은 과거 주를 백필할 수 있는 판매 순위만(최다 플레이는 Steam이 과거 기록을 주지 않음)
PERIOD_SOURCES = (ChartSource.TOP_SELLERS,)
GENRE_BASIS = (ChartSource.TOP_SELLERS, ChartSource.MOST_PLAYED)
MAX_POINTS = 101  # 주마다 101 − 순위점(1위 100점, 100위 1점)


class Period(StrEnum):
    MONTH = "MONTH"
    YEAR = "YEAR"


PERIOD_WEEKS = {Period.MONTH: 4, Period.YEAR: 52}
# 표 안 추이 그래프: 판매 순위는 최근 12주 순위, 현재 접속은 최근 7일을 3시간 단위로
SALES_TREND_WEEKS = 12
CONCURRENT_TREND = timedelta(days=7)
CONCURRENT_BUCKET = timedelta(hours=3)
PEAK_WINDOW = timedelta(hours=24)


class DashboardEntry(CamelModel):
    rank: int
    appid: int
    name: str
    image_url: str | None
    # 양수 = 지난주보다 상승. 주간 차트에서 지난주 순위가 없으면 is_new
    rank_delta: int | None
    is_new: bool
    metric_value: int | None
    final_price: int | None
    original_price: int | None
    discount_percent: int | None
    currency: str | None
    genres: list[str]
    # 월간·연간 합산 순위에서만: 합산 점수, 순위권에 든 주 수, 기간 내 최고 순위
    score: int | None = None
    weeks_charted: int | None = None
    best_rank: int | None = None
    # 추이 그래프 값(섹션의 trend_times와 같은 순서, 순위권 밖·수집 없음은 None). 추이가 없는 섹션은 None
    trend: list[int | None] | None = None
    # 현재 접속 섹션만: 수집한 범위 안의 최근 24시간 최고 동시 접속
    day_peak: int | None = None
    owned: bool | None = None
    affinity: float | None = None


class PeriodRanking(CamelModel):
    period: Period
    weeks_included: int
    weeks_required: int
    entries: list[DashboardEntry]


class DashboardSection(CamelModel):
    source: ChartSource
    snapshot_at: datetime
    period_start: datetime | None
    entries: list[DashboardEntry]
    # 주간 차트만: 월간·연간 합산 순위
    periods: list[PeriodRanking] = Field(default_factory=list)
    # 추이 그래프의 시간 축(오래된 것 → 최신). 판매 순위 = 주 시작일, 현재 접속 = 수집 시각
    trend_times: list[datetime] = Field(default_factory=list)


class GenreCount(CamelModel):
    genre: str
    count: int


class GenreDistribution(CamelModel):
    # 주간 판매·최다 플레이에 오른 게임 중 장르를 아는 게임 기준
    genres: list[GenreCount]
    based_on: int
    with_genres: int


class DashboardResponse(CamelModel):
    sections: list[DashboardSection]
    genre_distribution: GenreDistribution
    personalized: bool


@dataclass(frozen=True)
class PersonalContext:
    owned_appids: frozenset[int]
    preference: Mapping[str, float]


@dataclass
class _Aggregate:
    appid: int
    score: int = 0
    weeks: int = 0
    best_rank: int = 10_000
    latest: ChartEntry | None = None
    latest_period: datetime | None = None


@dataclass
class _Cache:
    value: DashboardResponse | None = None
    expires: float = 0.0


async def build_personal_context(
    api: SteamWebApi, owned_cache: OwnedGamesCache, metadata: MetadataLookup, steam_id: str
) -> PersonalContext | None:
    """보유 목록·취향을 만든다. 비공개·Steam 오류면 None(대시보드는 개인화 없이 보여준다)."""
    try:
        body = await owned_cache.get(api, steam_id)
    except AppError as exc:
        logger.info("dashboard personalization skipped: %s", exc.code)
        return None
    if body.games is None:
        return None
    meta = await metadata.lookup((g.appid for g in body.games), Priority.HIGH)
    genres_by_appid = {a: m.genres for a, m in meta.items() if m.status is FetchStatus.SUCCESS}
    return PersonalContext(
        owned_appids=frozenset(g.appid for g in body.games),
        preference=genre_preference(((g.appid, g.playtime_forever) for g in body.games), genres_by_appid),
    )


class DashboardService:
    def __init__(
        self,
        sessionmaker: Callable[[], async_sessionmaker[AsyncSession]],
        metadata: MetadataLookup,
        cc: str,
        entries_per_section: int = 20,
        cache_seconds: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._metadata = metadata
        self._cc = cc
        self._limit = entries_per_section
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._cache = _Cache()

    async def build(self, personal: PersonalContext | None) -> DashboardResponse:
        public = await self._public()
        result = _personalize(public, personal) if personal else public
        # 매칭도 계산은 영어 장르명으로 끝낸 뒤, 응답 직전에만 한국어 표시명으로 바꾼다.
        return _localize(result)

    async def _public(self) -> DashboardResponse:
        if self._cache.value is not None and self._clock() < self._cache.expires:
            return self._cache.value
        value = await self._build_public()
        self._cache = _Cache(value=value, expires=self._clock() + self._cache_seconds)
        return value

    async def _build_public(self) -> DashboardResponse:
        latest = await self._latest_snapshots()
        if not latest:
            raise AppError(ErrorCode.DATA_NOT_READY, "인기 게임 데이터를 수집하는 중입니다. 잠시 후 다시 시도해 주세요.", 503)
        history = await self._weekly_history(latest)
        trends = {
            ChartSource.TOP_SELLERS: _sales_trend(history.get(ChartSource.TOP_SELLERS, [])),
            ChartSource.CONCURRENT: _concurrent_trend(await self._concurrent_history(latest)),
        }

        sections_raw: list[tuple[ChartSnapshot, list[ChartEntry], dict[Period, tuple[int, list[_Aggregate]]]]] = []
        displayed: set[int] = set()
        for source in SECTION_ORDER:
            if source not in latest:
                continue
            snap = latest[source]
            current = sorted(snap.entries, key=lambda e: e.rank)[: self._limit]
            displayed.update(e.appid for e in current)
            periods = {}
            if source in PERIOD_SOURCES:
                for period, weeks in PERIOD_WEEKS.items():
                    included, ranked = _aggregate(history.get(source, []), weeks)
                    ranked = ranked[: self._limit]
                    displayed.update(a.appid for a in ranked)
                    periods[period] = (included, ranked)
            sections_raw.append((snap, current, periods))

        # 화면에 보이는 게임은 높은 우선순위, 장르 분포용 나머지는 낮은 우선순위로 보강한다.
        meta = await self._metadata.lookup(displayed, Priority.HIGH)
        basis = {e.appid for src in GENRE_BASIS if src in latest for e in latest[src].entries}
        meta = {**await self._metadata.lookup(basis - displayed, Priority.LOW), **meta}

        sections = []
        for snap, current, periods in sections_raw:
            weekly = snap.source in WEEKLY
            trend = trends.get(snap.source)

            def with_trend(entry: DashboardEntry, trend: _Trend | None = trend) -> DashboardEntry:
                if trend is None:
                    return entry
                return entry.model_copy(
                    update={"trend": trend.values(entry.appid), "day_peak": trend.peaks.get(entry.appid)}
                )

            sections.append(
                DashboardSection(
                    source=snap.source,
                    snapshot_at=snap.captured_at,
                    period_start=snap.period_start,
                    entries=[with_trend(_entry(e, meta.get(e.appid), weekly)) for e in current],
                    periods=[
                        PeriodRanking(
                            period=period,
                            weeks_included=included,
                            weeks_required=PERIOD_WEEKS[period],
                            entries=[
                                with_trend(_aggregate_entry(i + 1, a, meta.get(a.appid)))
                                for i, a in enumerate(ranked)
                            ],
                        )
                        for period, (included, ranked) in periods.items()
                    ],
                    trend_times=trend.times if trend else [],
                )
            )
        return DashboardResponse(
            sections=sections, genre_distribution=_genre_distribution(basis, meta), personalized=False
        )

    async def _latest_snapshots(self) -> dict[ChartSource, ChartSnapshot]:
        latest_ids = latest_success_ids(self._cc)
        async with self._sessionmaker()() as session:
            rows = await session.scalars(
                select(ChartSnapshot).where(ChartSnapshot.id.in_(latest_ids)).options(selectinload(ChartSnapshot.entries))
            )
            return {s.source: s for s in rows}

    async def _weekly_history(self, latest: Mapping[ChartSource, ChartSnapshot]) -> dict[ChartSource, list[ChartSnapshot]]:
        """기간 집계 대상 차트의 최근 52주 성공 스냅샷(같은 주는 가장 늦게 수집한 1개)."""
        result: dict[ChartSource, list[ChartSnapshot]] = {}
        async with self._sessionmaker()() as session:
            for source in PERIOD_SOURCES:
                anchor = latest.get(source)
                if anchor is None or anchor.period_start is None:
                    continue
                since = anchor.period_start - timedelta(weeks=PERIOD_WEEKS[Period.YEAR] - 1)
                rows = await session.scalars(
                    select(ChartSnapshot)
                    .where(ChartSnapshot.source == source, ChartSnapshot.cc == self._cc)
                    .where(ChartSnapshot.status == SnapshotStatus.SUCCESS, ChartSnapshot.period_start >= since)
                    .order_by(ChartSnapshot.captured_at)
                    .options(selectinload(ChartSnapshot.entries))
                )
                by_week: dict[tuple[int, int], ChartSnapshot] = {}
                for snap in rows:
                    by_week[snap.period_start.isocalendar()[:2]] = snap  # 같은 주는 나중 수집본으로 덮어씀
                result[source] = sorted(by_week.values(), key=lambda s: s.period_start, reverse=True)
        return result


    async def _concurrent_history(self, latest: Mapping[ChartSource, ChartSnapshot]) -> list[ChartSnapshot]:
        """현재 접속 차트의 최근 7일 성공 스냅샷(오래된 것 → 최신)."""
        anchor = latest.get(ChartSource.CONCURRENT)
        if anchor is None:
            return []
        async with self._sessionmaker()() as session:
            rows = await session.scalars(
                select(ChartSnapshot)
                .where(ChartSnapshot.source == ChartSource.CONCURRENT, ChartSnapshot.cc == self._cc)
                .where(ChartSnapshot.status == SnapshotStatus.SUCCESS)
                .where(ChartSnapshot.captured_at > anchor.captured_at - CONCURRENT_TREND)
                .order_by(ChartSnapshot.captured_at)
                .options(selectinload(ChartSnapshot.entries))
            )
            return list(rows)


@dataclass(frozen=True)
class _Trend:
    times: list[datetime]
    by_appid: dict[int, list[int | None]]
    peaks: dict[int, int]

    def values(self, appid: int) -> list[int | None]:
        return self.by_appid.get(appid, [None] * len(self.times))


def _sales_trend(weeks_desc: list[ChartSnapshot]) -> _Trend:
    """최근 12주 주간 순위(순위권 밖이면 None)."""
    weeks = list(reversed(weeks_desc[:SALES_TREND_WEEKS]))
    return _series(weeks, [w.period_start for w in weeks], lambda e: e.rank, peaks={})


def _concurrent_trend(snaps_asc: list[ChartSnapshot]) -> _Trend:
    """최근 7일 동시 접속을 3시간 단위로(구간마다 가장 늦은 수집본). 24시간 최고치는 모든 수집본 기준."""
    buckets: dict[int, ChartSnapshot] = {}
    for snap in snaps_asc:
        buckets[int(snap.captured_at.timestamp() // CONCURRENT_BUCKET.total_seconds())] = snap
    sampled = [buckets[k] for k in sorted(buckets)]
    peaks: dict[int, int] = {}
    if snaps_asc:
        since = snaps_asc[-1].captured_at - PEAK_WINDOW
        for snap in snaps_asc:
            if snap.captured_at <= since:
                continue
            for e in snap.entries:
                if e.metric_value is not None:
                    peaks[e.appid] = max(peaks.get(e.appid, 0), e.metric_value)
    return _series(sampled, [s.captured_at for s in sampled], lambda e: e.metric_value, peaks)


def _series(snaps: list[ChartSnapshot], times: list[datetime], value, peaks: dict[int, int]) -> _Trend:
    by_appid: dict[int, list[int | None]] = {}
    for i, snap in enumerate(snaps):
        for e in snap.entries:
            by_appid.setdefault(e.appid, [None] * len(snaps))[i] = value(e)
    return _Trend(times=times, by_appid=by_appid, peaks=peaks)


def _aggregate(weeks_desc: list[ChartSnapshot], weeks: int) -> tuple[int, list[_Aggregate]]:
    """최근 weeks주의 주간 순위를 점수로 합산한다. (포함된 주 수, 점수 순 목록)"""
    window = weeks_desc[:weeks]
    totals: dict[int, _Aggregate] = {}
    for snap in window:
        for entry in snap.entries:
            agg = totals.setdefault(entry.appid, _Aggregate(entry.appid))
            agg.score += max(0, MAX_POINTS - entry.rank)
            agg.weeks += 1
            agg.best_rank = min(agg.best_rank, entry.rank)
            if agg.latest_period is None or snap.period_start > agg.latest_period:
                agg.latest, agg.latest_period = entry, snap.period_start
    ranked = sorted(totals.values(), key=lambda a: (-a.score, a.best_rank, a.appid))
    return len(window), ranked


def _image(entry_image: str | None, meta: MetadataSnapshot | None) -> str | None:
    # appdetails의 정확한 주소 → 소스가 준 주소(추정일 수 있음) 순서. 주소만 내려주고 이미지는 저장하지 않는다.
    return (meta.header_image if meta and meta.header_image else None) or entry_image


def _genres(meta: MetadataSnapshot | None) -> list[str]:
    return list(meta.genres) if meta and meta.status is FetchStatus.SUCCESS else []


def _name(entry_name: str | None, appid: int, meta: MetadataSnapshot | None) -> str:
    return entry_name or (meta.name if meta and meta.name else f"App {appid}")


def _entry(e: ChartEntry, meta: MetadataSnapshot | None, weekly: bool) -> DashboardEntry:
    return DashboardEntry(
        rank=e.rank,
        appid=e.appid,
        name=_name(e.name, e.appid, meta),
        image_url=_image(e.image_url, meta),
        rank_delta=(e.last_week_rank - e.rank) if weekly and e.last_week_rank else None,
        is_new=weekly and not e.last_week_rank,
        metric_value=e.metric_value,
        final_price=e.final_price,
        original_price=e.original_price,
        discount_percent=e.discount_percent,
        currency=e.currency,
        genres=_genres(meta),
    )


def _aggregate_entry(rank: int, agg: _Aggregate, meta: MetadataSnapshot | None) -> DashboardEntry:
    latest = agg.latest
    return DashboardEntry(
        rank=rank,
        appid=agg.appid,
        name=_name(latest.name if latest else None, agg.appid, meta),
        image_url=_image(latest.image_url if latest else None, meta),
        rank_delta=None,
        is_new=False,
        metric_value=None,
        final_price=None,
        original_price=None,
        discount_percent=None,
        currency=None,
        genres=_genres(meta),
        score=agg.score,
        weeks_charted=agg.weeks,
        best_rank=agg.best_rank,
    )


def _personalize(public: DashboardResponse, personal: PersonalContext) -> DashboardResponse:
    def mark(entries: list[DashboardEntry]) -> list[DashboardEntry]:
        return [
            e.model_copy(
                update={
                    "owned": e.appid in personal.owned_appids,
                    "affinity": affinity(personal.preference, e.genres) if e.genres else None,
                }
            )
            for e in entries
        ]

    sections = [
        s.model_copy(
            update={
                "entries": mark(s.entries),
                "periods": [p.model_copy(update={"entries": mark(p.entries)}) for p in s.periods],
            }
        )
        for s in public.sections
    ]
    return public.model_copy(update={"sections": sections, "personalized": True})


def _localize(resp: DashboardResponse) -> DashboardResponse:
    def entries(items: list[DashboardEntry]) -> list[DashboardEntry]:
        return [e.model_copy(update={"genres": korean_genres(e.genres)}) for e in items]

    sections = [
        s.model_copy(
            update={
                "entries": entries(s.entries),
                "periods": [p.model_copy(update={"entries": entries(p.entries)}) for p in s.periods],
            }
        )
        for s in resp.sections
    ]
    dist = resp.genre_distribution.model_copy(
        update={"genres": [g.model_copy(update={"genre": korean_genre(g.genre)}) for g in resp.genre_distribution.genres]}
    )
    return resp.model_copy(update={"sections": sections, "genre_distribution": dist})


def _genre_distribution(appids: Iterable[int], meta: Mapping[int, MetadataSnapshot]) -> GenreDistribution:
    ids = list(appids)
    known = [meta[a] for a in ids if a in meta and meta[a].status is FetchStatus.SUCCESS]
    counts = Counter(g for m in known for g in set(m.genres))
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return GenreDistribution(
        genres=[GenreCount(genre=g, count=c) for g, c in top],
        based_on=len(ids),
        with_genres=len(known),
    )

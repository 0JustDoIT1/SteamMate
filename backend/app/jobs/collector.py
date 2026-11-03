"""대시보드 차트 주기 수집.

- PostgreSQL advisory lock으로 동시에 한 번만 실행한다(여러 워커·수동 실행 대비).
- 소스별 갱신 간격이 지나지 않았거나, 주간 차트의 집계일이 같으면 건너뛴다.
- 실패는 FAILED 스냅샷으로 남기고, 대시보드는 마지막 SUCCESS를 계속 보여준다.
- 판매 순위는 과거 주차 조회가 가능해 빠진 주(최근 52주)를 채운다(월간·연간 집계용).
- 수집한 게임은 메타데이터 캐시에 낮은 우선순위로 보강을 요청한다(사용자 요청이 먼저).
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chart_queries import latest_success_ids
from app.metadata.service import MetadataLookup, Priority
from app.models import ChartEntry, ChartSnapshot, ChartSource, SnapshotStatus
from app.steam.charts_api import ChartFetch, ChartsApi

logger = logging.getLogger(__name__)

LOCK_KEY = 0x5354_4D43  # "STMC": 수집 작업 전용 advisory lock 키
WEEKLY = (ChartSource.TOP_SELLERS, ChartSource.MOST_PLAYED)
BACKFILL_WEEKS = 52


@dataclass(frozen=True)
class CollectorPolicy:
    intervals: dict[ChartSource, timedelta]
    # 소스별 보관 기간. 주간 차트는 집계 주(period_start) 기준, 나머지는 수집 시각 기준.
    retention: dict[ChartSource, timedelta]


@dataclass
class CollectReport:
    ran: bool = False
    stored: list[ChartSource] | None = None
    skipped: list[ChartSource] | None = None
    failed: list[ChartSource] | None = None
    backfilled: int = 0


class Collector:
    def __init__(
        self,
        sessionmaker: Callable[[], async_sessionmaker[AsyncSession]],
        charts: ChartsApi,
        metadata: MetadataLookup,
        policy: CollectorPolicy,
        cc: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessionmaker = sessionmaker
        self._charts = charts
        self._metadata = metadata
        self._policy = policy
        self._cc = cc
        self._now = now

    async def run_once(self) -> CollectReport:
        report = CollectReport(stored=[], skipped=[], failed=[])
        appids: set[int] = set()
        async with self._sessionmaker()() as session, session.begin():
            # 트랜잭션 단위 잠금: commit/rollback 시 자동 해제되므로 해제 누락·연결 교체 문제가 없다.
            locked = await session.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
            if not locked:
                logger.info("collector already running elsewhere, skipping")
                return report
            report.ran = True
            top_sellers_due = await self._is_due(session, ChartSource.TOP_SELLERS, self._now())
            appids = await self._collect(session, report)
            if top_sellers_due:
                # 판매 순위 갱신 주기(기본 6시간)에만 과거 주를 채워, 받지 못한 주를 매시간 재요청하지 않는다.
                report.backfilled = await self._backfill_top_sellers(session)
            await self._cleanup(session)
        # 잠금·트랜잭션이 끝난 뒤 보강을 요청한다(메타데이터 서비스는 자체 세션을 쓴다).
        if appids:
            await self._metadata.lookup(appids, Priority.LOW)
        logger.info("collector done stored=%s skipped=%s failed=%s", report.stored, report.skipped, report.failed)
        return report

    async def _collect(self, session: AsyncSession, report: CollectReport) -> set[int]:
        now = self._now()
        due = [s for s in ChartSource if await self._is_due(session, s, now)]
        report.skipped.extend(s for s in ChartSource if s not in due)
        fetches: list[ChartFetch] = []
        if ChartSource.TOP_SELLERS in due:
            fetches.append(await self._charts.top_sellers())
        if ChartSource.MOST_PLAYED in due:
            fetches.append(await self._charts.most_played())
        if ChartSource.CONCURRENT in due:
            fetches.append(await self._charts.concurrent())
        if ChartSource.SPECIALS in due or ChartSource.NEW_RELEASES in due:
            fetches.extend(f for f in await self._charts.featured() if f.source in due)

        appids: set[int] = set()
        for fetch in fetches:
            if fetch.failure:
                session.add(_snapshot(fetch, self._cc, now, SnapshotStatus.FAILED))
                report.failed.append(fetch.source)
                logger.warning("chart fetch failed: %s %s", fetch.source, fetch.failure)
                continue
            if fetch.source in WEEKLY and await self._same_period(session, fetch):
                report.skipped.append(fetch.source)
                continue
            snapshot = _snapshot(fetch, self._cc, now, SnapshotStatus.SUCCESS)
            snapshot.entries = [ChartEntry(**vars(item)) for item in fetch.items]
            session.add(snapshot)
            report.stored.append(fetch.source)
            appids.update(item.appid for item in fetch.items)
        await session.flush()
        return appids

    async def _is_due(self, session: AsyncSession, source: ChartSource, now: datetime) -> bool:
        last = await session.scalar(
            select(ChartSnapshot.captured_at)
            .where(ChartSnapshot.source == source, ChartSnapshot.cc == self._cc)
            .where(ChartSnapshot.status == SnapshotStatus.SUCCESS)
            .order_by(ChartSnapshot.captured_at.desc())
            .limit(1)
        )
        return last is None or now - last >= self._policy.intervals[source]

    async def _same_period(self, session: AsyncSession, fetch: ChartFetch) -> bool:
        if fetch.period_start is None:
            return False
        return fetch.period_start in await self._stored_periods(session, fetch.source)

    async def _stored_periods(self, session: AsyncSession, source: ChartSource) -> set[datetime]:
        rows = await session.scalars(
            select(ChartSnapshot.period_start)
            .where(ChartSnapshot.source == source, ChartSnapshot.cc == self._cc)
            .where(ChartSnapshot.status == SnapshotStatus.SUCCESS, ChartSnapshot.period_start.is_not(None))
        )
        return set(rows)

    async def _backfill_top_sellers(self, session: AsyncSession) -> int:
        """가장 최근 주를 기준으로 지난 51주 중 없는 주를 채운다. 실패한 주는 다음 실행에서 다시 시도."""
        stored = await self._stored_periods(session, ChartSource.TOP_SELLERS)
        if not stored:
            return 0  # 현재 주를 먼저 받아야 기준 주를 안다
        anchor = max(stored)
        # 보관 기간 밖의 주는 받아도 곧 정리되므로 채우지 않는다(삭제·재수집 반복 방지).
        keep_since = self._now() - self._policy.retention[ChartSource.TOP_SELLERS]
        missing = [anchor - timedelta(weeks=k) for k in range(1, BACKFILL_WEEKS)]
        missing = [week for week in missing if week not in stored and week >= keep_since]
        filled = 0
        for week in missing:
            fetch = await self._charts.top_sellers(start_date=week)
            if fetch.failure or fetch.period_start is None or fetch.period_start in stored:
                if fetch.failure:
                    logger.warning("top sellers backfill failed for %s: %s", week.date(), fetch.failure)
                continue
            snapshot = _snapshot(fetch, self._cc, self._now(), SnapshotStatus.SUCCESS)
            snapshot.entries = [ChartEntry(**vars(item)) for item in fetch.items]
            session.add(snapshot)
            stored.add(fetch.period_start)
            filled += 1
        await session.flush()
        return filled

    async def _cleanup(self, session: AsyncSession) -> None:
        now = self._now()
        # 소스별 최신 성공본은 오래되어도 남긴다(집계일이 바뀌지 않아 새로 저장되지 않는 경우 대비).
        latest_success = latest_success_ids()
        for source, keep in self._policy.retention.items():
            # 백필한 과거 주는 수집 시각이 최근이므로, 주간 차트는 집계 주 기준으로 판단한다.
            age_basis = func.coalesce(ChartSnapshot.period_start, ChartSnapshot.captured_at)
            await session.execute(
                delete(ChartSnapshot).where(
                    ChartSnapshot.source == source,
                    age_basis < now - keep,
                    ChartSnapshot.id.not_in(latest_success),
                )
            )


def _snapshot(fetch: ChartFetch, cc: str, now: datetime, status: SnapshotStatus) -> ChartSnapshot:
    return ChartSnapshot(
        source=fetch.source,
        cc=cc,
        captured_at=now,
        period_start=fetch.period_start,
        status=status,
        failure_reason=fetch.failure,
    )


async def run_periodically(collector: Collector, interval: timedelta, initial_delay: float = 5.0) -> None:
    """서버 수명 동안 주기 실행. 한 번의 실패가 루프를 멈추지 않게 한다."""
    await asyncio.sleep(initial_delay)
    while True:
        try:
            await collector.run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("collector run failed")
        await asyncio.sleep(interval.total_seconds())

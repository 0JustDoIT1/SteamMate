from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChartEntry, ChartSnapshot, ChartSource, SnapshotStatus


def latest_success_ids(cc: str | None = None) -> Select:
    """(source, cc)별 '최신' 성공 스냅샷 id. 수집 정리와 대시보드가 같은 정의를 쓴다.

    최신 = 집계 주가 가장 늦은 것, 같으면 가장 늦게 수집한 것. id 최댓값을 쓰면 안 된다:
    과거 주를 백필하면 오래된 주가 더 큰 id를 갖기 때문이다.
    """
    q = (
        select(ChartSnapshot.id)
        .where(ChartSnapshot.status == SnapshotStatus.SUCCESS)
        .ext(distinct_on(ChartSnapshot.source, ChartSnapshot.cc))
        .order_by(
            ChartSnapshot.source,
            ChartSnapshot.cc,
            ChartSnapshot.period_start.desc().nulls_last(),
            ChartSnapshot.captured_at.desc(),
        )
    )
    return q.where(ChartSnapshot.cc == cc) if cc else q


@dataclass(frozen=True)
class PoolEntry:
    """미보유 게임 추천 후보 1개. 여러 목록에 오르면 가장 높은 순위를 남긴다."""

    appid: int
    best_rank: int
    source: ChartSource
    name: str | None


async def candidate_pool(session: AsyncSession, cc: str, top_seller_weeks: int = 4) -> tuple[dict[int, PoolEntry], datetime | None]:
    """(appid → 후보, 기준 시각). 후보 = 소스별 최신 목록 + 최근 N주 판매 순위(PRD F4ⓒ 후보 풀).

    기준 시각은 쓰인 최신 스냅샷들의 가장 늦은 수집 시각. 수집 전이면 ({}, None).
    """
    latest = (await session.scalars(latest_success_ids(cc))).all()
    if not latest:
        return {}, None
    snapshot_ids = set(latest)
    newest_week = await session.scalar(
        select(func.max(ChartSnapshot.period_start)).where(
            ChartSnapshot.source == ChartSource.TOP_SELLERS,
            ChartSnapshot.cc == cc,
            ChartSnapshot.status == SnapshotStatus.SUCCESS,
        )
    )
    if newest_week is not None:
        recent_weeks = await session.scalars(
            select(ChartSnapshot.id).where(
                ChartSnapshot.source == ChartSource.TOP_SELLERS,
                ChartSnapshot.cc == cc,
                ChartSnapshot.status == SnapshotStatus.SUCCESS,
                ChartSnapshot.period_start > newest_week - timedelta(weeks=top_seller_weeks),
            )
        )
        snapshot_ids.update(recent_weeks)

    rows = await session.execute(
        select(ChartEntry.appid, ChartEntry.rank, ChartEntry.name, ChartSnapshot.source)
        .join(ChartSnapshot, ChartSnapshot.id == ChartEntry.snapshot_id)
        .where(ChartEntry.snapshot_id.in_(snapshot_ids))
        # 같은 순위면 소스 정의 순(판매 순위가 먼저, PostgreSQL enum 순서)으로 정해 결과가 매번 같게 한다.
        .order_by(ChartEntry.rank, ChartSnapshot.source)
    )
    pool: dict[int, PoolEntry] = {}
    for appid, rank, name, source in rows:
        if appid not in pool:
            pool[appid] = PoolEntry(appid, rank, source, name)
    captured = await session.scalar(select(func.max(ChartSnapshot.captured_at)).where(ChartSnapshot.id.in_(latest)))
    return pool, captured
